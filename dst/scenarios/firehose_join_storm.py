import asyncio
import logging
import os

os.environ.setdefault("BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("DATABASE_URL", "mysql+asyncmy://sim:sim@localhost/sim")

from bot_detector.firehose.api.firehose import firehose as firehose_route  # noqa: E402
from bot_detector.firehose.app.auth.auth import ANONYMOUS  # noqa: E402
from bot_detector.firehose.app.consumer.queue_repo import QueueRepo  # noqa: E402
from bot_detector.firehose.core.config import Settings  # noqa: E402
from bot_detector.firehose.core.server import create_app  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from dst import (  # noqa: E402
    KafkaFaultConfig,
    virtual_time,
)
from dst.loop import running_clock  # noqa: E402
from dst.payloads import (  # noqa: E402
    PayloadConfig,
    build_payload_pool,
)
from dst.scenarios.firehose_parity import (  # noqa: E402
    _GROUPS,
    TOPIC,
    FakeWebSocket,
    _counter,
    _drain,
    _make_consumer_patch,
)
from dst.systems import KafkaConfig  # noqa: E402

logger = logging.getLogger(__name__)


class JoinStormConfig(BaseModel):
    # total scenario length; joins land at i * join_interval_s, so keep
    # duration_s >= (n_clients - 1) * join_interval_s + one watch window
    duration_s: float = Field(default=75.0, gt=0.0)
    feed_rate_s: int = Field(default=1000, gt=0)
    pool_size: int = Field(default=200, ge=1)
    payload_seed: int = 42
    kafka_seed: int = 42
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
    """Run staggered joins into a hot anonymous firehose.

    The feed runs at full rate while clients join one by one, so each
    inbox fills faster than its client drains. The scenario exposes
    the interaction between the join grace, the kick rule (a lone
    subscriber can never be kicked for backpressure; two or more can),
    and the resulting kick wave: the report shows who survived, who
    was kicked, and when.
    """
    config = JoinStormConfig(**kwargs)
    with virtual_time():
        logging.getLogger("bot_detector").setLevel(logging.WARNING)
        clock = running_clock()
        kafka_config = KafkaConfig(
            seed=config.kafka_seed,
            feed_rate_s=config.feed_rate_s,
            faults=KafkaFaultConfig(),
        )
        pool = build_payload_pool(
            PayloadConfig(seed=config.payload_seed, pool_size=config.pool_size)
        )
        _GROUPS.clear()
        QueueRepo.create_consumer = _make_consumer_patch(  # type: ignore[assignment]
            kafka_config, pool
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
            if joined_at > clock.time():
                await asyncio.sleep(joined_at - clock.time())
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
                        user=ANONYMOUS,
                    ),
                    name=f"route-{i}",
                )
            )
            asyncio.create_task(
                _drain(websocket, config.client_slow_s, client_counts),
                name=f"drain-{i}",
            )

        if clock.time() < config.duration_s:
            await asyncio.sleep(config.duration_s - clock.time())

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
            duration_s=clock.time(),
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
