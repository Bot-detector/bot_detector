"""Join-storm scenario: staggered connects into a hot feed.

Rebuilds perf's ramp scenarios on the virtual clock: the feed runs at
full rate while clients join one by one. The scenario exposes the
interaction between the join grace, the kick rule (a lone subscriber
can never be kicked for backpressure; two or more can), and inboxes
that fill faster than their clients drain.

Expected shape with the documented command: every client joins a
stream that already runs at 1000 msg/s and drains at only 500 msg/s,
so its inbox fills within a second. During the join grace the excess
is dropped; once the grace is over and a second subscriber exists,
the inbox is kicked (close 1013). The first client starts as the lone
subscriber, which the pump protects - the report shows who survived,
who was kicked, and when.
"""

import asyncio
import logging
import os

os.environ.setdefault("BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("DATABASE_URL", "mysql+asyncmy://sim:sim@localhost/sim")

from bot_detector.firehose.api.firehose import firehose as firehose_route  # noqa: E402
from bot_detector.firehose.app.consumer.queue_repo import QueueRepo  # noqa: E402
from bot_detector.firehose.core.config import Settings  # noqa: E402
from bot_detector.firehose.core.server import create_app  # noqa: E402
from development.perf.firehose.payloads import (  # noqa: E402
    PayloadConfig,
    build_payload_pool,
)
from pydantic import BaseModel, Field  # noqa: E402

from dst import IoConfig, MachineConfig, VirtualMachine, virtual_time  # noqa: E402
from dst.scenarios.firehose import (  # noqa: E402
    TOPIC,
    FakeWebSocket,
    _GROUPS,
    _counter,
    _drain,
    _make_consumer_patch,
)
from dst.systems import KafkaConfig, KafkaFaults  # noqa: E402

logger = logging.getLogger(__name__)


class JoinStormConfig(BaseModel):
    # total scenario length; joins land at i * join_interval_s, so keep
    # duration_s >= (n_clients - 1) * join_interval_s + one watch window
    duration_s: float = Field(default=75.0, gt=0.0)
    feed_rate_s: int = Field(default=1000, gt=0)
    pool_size: int = Field(default=200, ge=1)
    payload_seed: int = 42
    kafka_seed: int = 42
    machine_seed: int = 7
    n_clients: int = Field(default=5, ge=1)
    join_interval_s: float = Field(default=15.0, gt=0.0)
    client_slow_s: float = Field(default=0.002, ge=0.0)
    client_buffer: int = Field(default=500, gt=0)
    kick_grace_s: float = Field(default=10.0, gt=0.0)


class JoinStormClient(BaseModel):
    name: str
    joined_at_s: float
    received: int
    sent: int
    close_code: int | None
    close_reason: str


class JoinStormReport(BaseModel):
    config: JoinStormConfig
    duration_s: float
    produced: int
    consumed: int
    backlog: int
    messages_delivered: int
    kicked: int
    dropped: int
    clients: list[JoinStormClient]


async def main(**kwargs) -> JoinStormReport:
    """Run staggered joins into a hot anonymous firehose."""
    config = JoinStormConfig(**kwargs)
    with virtual_time():
        logging.getLogger("bot_detector").setLevel(logging.WARNING)
        machine = VirtualMachine(
            MachineConfig(
                seed=config.machine_seed,
                io={"kafka": IoConfig(mean_ms=0.01, jitter_ms=0.005)},
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
        labels = {"topic": TOPIC, "type": "anonymous"}
        baseline = {
            "messages": _counter("firehose_messages_total", labels),
            "kicked": _counter("firehose_kicked_total", labels),
            "dropped": _counter("firehose_dropped_total", labels),
        }

        sockets: list[FakeWebSocket] = []
        routes: list[asyncio.Task] = []
        counts: list[list[int]] = []
        clients: list[JoinStormClient] = []
        for i in range(config.n_clients):
            joined_at = i * config.join_interval_s
            if joined_at > machine.clock.time():
                await asyncio.sleep(joined_at - machine.clock.time())
            websocket = FakeWebSocket(
                app, buffer_size=config.client_buffer, name=f"client-{i}"
            )
            client_counts: list[int] = [0]
            sockets.append(websocket)
            counts.append(client_counts)
            clients.append(
                JoinStormClient(
                    name=websocket.name,
                    joined_at_s=joined_at,
                    received=0,
                    sent=0,
                    close_code=None,
                    close_reason="",
                )
            )
            routes.append(
                asyncio.create_task(
                    firehose_route(
                        websocket=websocket,  # type: ignore[arg-type]
                        topic=TOPIC,
                    ),
                    name=f"route-{i}",
                )
            )
            asyncio.create_task(
                _drain(websocket, config.client_slow_s, client_counts),
                name=f"drain-{i}",
            )

        if machine.clock.time() < config.duration_s:
            await asyncio.sleep(config.duration_s - machine.clock.time())

        # wind down: close sockets so routes clean up, then stop feeds
        for websocket in sockets:
            await websocket.close(code=1000, reason="scenario end")
        await asyncio.gather(*routes, return_exceptions=True)
        for kafka in _GROUPS.values():
            await kafka.stop()

        feed = next(iter(_GROUPS.values()), None)
        for client, websocket, client_counts in zip(
            clients, sockets, counts, strict=True
        ):
            frame = websocket.close_frame
            client.received = client_counts[0]
            client.sent = websocket.sent_count
            client.close_code = frame["code"] if frame else None
            client.close_reason = frame["reason"] if frame else ""
        return JoinStormReport(
            config=config,
            duration_s=machine.clock.time(),
            produced=feed.produced_total if feed else 0,
            consumed=feed.consumed_total if feed else 0,
            backlog=feed.backlog if feed else 0,
            messages_delivered=int(
                _counter("firehose_messages_total", labels) - baseline["messages"]
            ),
            kicked=int(_counter("firehose_kicked_total", labels) - baseline["kicked"]),
            dropped=int(
                _counter("firehose_dropped_total", labels) - baseline["dropped"]
            ),
            clients=clients,
        )
