"""Keyed-client scenario: per-user groups stay clean while the shared
anonymous group degrades.

The discord token path is a seam like the broker: the scenario patches
``auth_repo.authenticate`` (the real one needs a discord OAuth call and
a database) to hand out ``discord_<token>`` users with the topic
permission. Everything after that seam is product code: per-user
consumer groups, the shared anonymous group, and the exchange.

The documented command pairs fast keyed clients with a slow anonymous
fleet on the same feed rate. The anonymous clients' shared inbox fills
and they take grace drops and kicks; every keyed client has its own
group, its own pump, and drains fast, so it must see the full stream
with no drops and no kicks. The report carries per-type counters and
per-group feed totals so the isolation is auditable.
"""

import asyncio
import logging
import os
import types
from collections.abc import Awaitable, Callable

os.environ.setdefault("BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("DATABASE_URL", "mysql+asyncmy://sim:sim@localhost/sim")

from bot_detector.firehose.api.firehose import firehose as firehose_route  # noqa: E402
from bot_detector.firehose.app.auth.auth import ANONYMOUS, AuthUser  # noqa: E402
from bot_detector.firehose.app.consumer.queue_repo import QueueRepo  # noqa: E402
from bot_detector.firehose.core.config import Settings  # noqa: E402
from bot_detector.firehose.core.server import create_app  # noqa: E402
from dst.payloads import (  # noqa: E402
    PayloadConfig,
    build_payload_pool,
)
from pydantic import BaseModel, Field  # noqa: E402

from dst import Machine, MachineConfig, NetworkConfig, virtual_time  # noqa: E402
from dst.scenarios.firehose import (  # noqa: E402
    TOPIC,
    FirehoseClientReport,
    FakeWebSocket,
    _GROUPS,
    _counter,
    _drain,
    _make_consumer_patch,
)
from dst.systems import KafkaConfig, KafkaFaults  # noqa: E402

logger = logging.getLogger(__name__)


class KeyedIsolationConfig(BaseModel):
    duration_s: float = Field(default=40.0, gt=0.0)
    feed_rate_s: int = Field(default=200, gt=0)
    pool_size: int = Field(default=100, ge=1)
    payload_seed: int = 42
    kafka_seed: int = 42
    machine_seed: int = 7
    n_keyed: int = Field(default=2, ge=0)
    n_anonymous: int = Field(default=3, ge=0)
    anonymous_slow_s: float = Field(default=0.02, ge=0.0)
    anonymous_buffer: int = Field(default=500, gt=0)
    keyed_buffer: int = Field(default=5000, gt=0)
    kick_grace_s: float = Field(default=10.0, gt=0.0)


class KeyedIsolationReport(BaseModel):
    config: KeyedIsolationConfig
    duration_s: float
    keyed_clients: list[FirehoseClientReport]
    anonymous_clients: list[FirehoseClientReport]
    keyed_messages: int
    keyed_kicked: int
    keyed_dropped: int
    anonymous_messages: int
    anonymous_kicked: int
    anonymous_dropped: int
    produced_per_group: dict[str, int]


def _make_auth_patch() -> Callable[..., Awaitable[AuthUser]]:
    """Authenticate key-<n> tokens as discord users; everyone anonymous.

    Mirrors the product contract: a registered, allowlisted token maps
    to ``discord_<identity>`` with the topic permission; an absent
    token maps to the shared anonymous user.
    """

    async def authenticate(self: object, api_key: str | None, topic: str) -> AuthUser:
        if api_key and api_key.startswith("key-"):
            return AuthUser(
                name=f"discord_{api_key.removeprefix('key-')}",
                scopes=[f"firehose.{topic}"],
            )
        return ANONYMOUS

    return authenticate


async def main(**kwargs) -> KeyedIsolationReport:
    """Run fast keyed users next to a slow anonymous fleet."""
    config = KeyedIsolationConfig(**kwargs)
    with virtual_time():
        logging.getLogger("bot_detector").setLevel(logging.WARNING)
        machine = Machine(
            MachineConfig(
                seed=config.machine_seed,
                network=NetworkConfig(mean_ms=0.01, jitter_ms=0.005),
            )
        )
        kafka_config = KafkaConfig(
            seed=config.kafka_seed,
            rate_s=config.feed_rate_s,
            faults=KafkaFaults(),
        )
        pool = build_payload_pool(
            PayloadConfig(seed=config.payload_seed, pool_size=config.pool_size)
        )
        _GROUPS.clear()
        QueueRepo.create_consumer = _make_consumer_patch(  # type: ignore[assignment]
            machine, kafka_config, pool
        )
        app = create_app(
            Settings(port=0, metrics_port=0, kick_grace_s=config.kick_grace_s)
        )
        state = app.state.firehose
        state.auth_repo.authenticate = types.MethodType(  # type: ignore[method-assign]
            _make_auth_patch(), state.auth_repo
        )
        base = {
            kind: {
                name: _counter(name, {"topic": TOPIC, "type": kind})
                for name in (
                    "firehose_messages_total",
                    "firehose_kicked_total",
                    "firehose_dropped_total",
                )
            }
            for kind in ("anonymous", "keyed")
        }

        sockets: list[FakeWebSocket] = []
        routes: list[asyncio.Task] = []
        drains: list[asyncio.Task] = []
        counts: list[list[int]] = []
        for i in range(config.n_keyed):
            websocket = FakeWebSocket(
                app,
                buffer_size=config.keyed_buffer,
                name=f"keyed-{i}",
                api_key=f"key-user{i}",
                force_anonymous=False,
            )
            client_counts: list[int] = [0]
            sockets.append(websocket)
            counts.append(client_counts)
            routes.append(_route_task(websocket, f"keyed-{i}"))
            drains.append(_drain_task(websocket, client_counts, 0.0, f"keyed-{i}"))
        for i in range(config.n_anonymous):
            websocket = FakeWebSocket(
                app,
                buffer_size=config.anonymous_buffer,
                name=f"anon-{i}",
            )
            anon_counts: list[int] = [0]
            sockets.append(websocket)
            counts.append(anon_counts)
            routes.append(_route_task(websocket, f"anon-{i}"))
            drains.append(
                _drain_task(
                    websocket, anon_counts, config.anonymous_slow_s, f"anon-{i}"
                )
            )

        await asyncio.sleep(config.duration_s)

        for websocket in sockets:
            await websocket.close(code=1000, reason="scenario end")
        await asyncio.gather(*routes, *drains, return_exceptions=True)
        for kafka in _GROUPS.values():
            await kafka.stop()

        produced_per_group = {
            group: kafka.produced_total for group, kafka in _GROUPS.items()
        }

        def client_reports(prefix: str) -> list[FirehoseClientReport]:
            return [
                FirehoseClientReport(
                    name=websocket.name,
                    received=counts[j][0],
                    sent=websocket.sent_count,
                    close_code=(
                        websocket.close_frame["code"] if websocket.close_frame else None
                    ),
                    close_reason=(
                        websocket.close_frame["reason"] if websocket.close_frame else ""
                    ),
                )
                for j, websocket in enumerate(sockets)
                if websocket.name.startswith(prefix)
            ]

        def delta(kind: str, metric: str) -> int:
            name = {
                "messages": "firehose_messages_total",
                "kicked": "firehose_kicked_total",
                "dropped": "firehose_dropped_total",
            }[metric]
            return int(
                _counter(name, {"topic": TOPIC, "type": kind}) - base[kind][name]
            )

        return KeyedIsolationReport(
            config=config,
            duration_s=machine.clock.time(),
            keyed_clients=client_reports("keyed-"),
            anonymous_clients=client_reports("anon-"),
            keyed_messages=delta("keyed", "messages"),
            keyed_kicked=delta("keyed", "kicked"),
            keyed_dropped=delta("keyed", "dropped"),
            anonymous_messages=delta("anonymous", "messages"),
            anonymous_kicked=delta("anonymous", "kicked"),
            anonymous_dropped=delta("anonymous", "dropped"),
            produced_per_group=produced_per_group,
        )


def _route_task(websocket: FakeWebSocket, name: str) -> asyncio.Task:
    return asyncio.create_task(
        firehose_route(
            websocket=websocket,  # type: ignore[arg-type]
            topic=TOPIC,
        ),
        name=f"route-{name}",
    )


def _drain_task(
    websocket: FakeWebSocket, counts: list[int], slow_s: float, name: str
) -> asyncio.Task:
    return asyncio.create_task(_drain(websocket, slow_s, counts), name=f"drain-{name}")
