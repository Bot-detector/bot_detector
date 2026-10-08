"""The real firehose app on the DST virtual clock.

The production pump, Exchange, connection manager and websocket route
all run unmodified; only the I/O seams are replaced:

- kafka: QueueRepo.create_consumer is patched to a FakeKafka-backed
  adapter. Payloads come from the deterministic pool in dst.payloads,
  so a run replays byte-identically per seed.
- websockets: FakeWebSocket plays the uvicorn side of the ASGI
  interface (handshake event, receive(), send_text with backpressure,
  close codes). A drainer task per client models the peer reading at
  its own speed; a slow drainer fills the outbox, the route's send
  times out (ConnectionManager) or the Exchange kicks the inbox -
  whichever policy fires first on the virtual timeline.
- time: virtual_time() patches time.monotonic for the whole scenario
  so the Exchange's join-grace math (Inbox.age_s) runs on the clock.

The scenario never starts uvicorn and never opens a socket.
"""

import asyncio
import logging
import os
import time
from collections.abc import Callable
from typing import Any

os.environ.setdefault("BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("DATABASE_URL", "mysql+asyncmy://sim:sim@localhost/sim")

import orjson  # noqa: E402
from bot_detector.firehose.api.firehose import (  # noqa: E402
    firehose as firehose_route,
)
from bot_detector.firehose.app.consumer.queue_repo import QueueRepo  # noqa: E402
from bot_detector.firehose.app.consumer.structs import TOPIC_MODELS  # noqa: E402
from bot_detector.firehose.app.exchange.structs import Inbox  # noqa: E402
from bot_detector.firehose.core.config import Settings  # noqa: E402
from bot_detector.firehose.core.server import create_app  # noqa: E402
from dst.payloads import (  # noqa: E402
    PayloadConfig,
    build_payload_pool,
)
from prometheus_client import REGISTRY  # noqa: E402
from pydantic import BaseModel, Field, ValidationError  # noqa: E402

from dst import (  # noqa: E402
    Machine,
    MachineConfig,
    NetworkConfig,
    virtual_time,
)
from dst.systems import (  # noqa: E402
    FakeKafka,
    KafkaConfig,
    KafkaFaults,
    KafkaMessage,
)

logger = logging.getLogger(__name__)

TOPIC = "players.scraped"


def _virtualize_inbox_clock() -> None:
    """Point Inbox.subscribed_at's default factory at the patched clock.

    The generated dataclass __init__ resolves default factories through
    a closure cell captured at class creation (the real time.monotonic).
    The Exchange's join-grace math (Inbox.age_s) must run on the virtual
    clock, so rebind that cell to a call that resolves time.monotonic
    lazily - inside virtual_time() it returns virtual time.
    """
    original = Inbox.__dataclass_fields__["subscribed_at"].default_factory
    for cell in Inbox.__init__.__closure__ or ():
        try:
            if cell.cell_contents is original:
                cell.cell_contents = lambda: time.monotonic()
                return
        except ValueError:  # empty cell
            continue
    raise RuntimeError("could not rebind Inbox.subscribed_at default factory")


_virtualize_inbox_clock()


class FakeKafkaQueueConsumer:
    """QueueConsumer-protocol adapter over a DST FakeKafka.

    Same surface the pump uses (start/stop/get_one), same value path
    as the kafka adapter: deserialize then validate, errors as values.
    """

    def __init__(self, kafka: FakeKafka, model: type[BaseModel]):
        self._kafka = kafka
        self._model = model

    async def start(self) -> None:
        await self._kafka.start()

    async def stop(self) -> None:
        await self._kafka.stop()

    async def get_one(self) -> BaseModel | Exception | None:
        item = await self._kafka.get_one()
        if not isinstance(item, KafkaMessage):
            return item  # FakeKafkaError: the pump's fault path
        try:
            return self._model.model_validate(orjson.loads(item.payload))
        except ValidationError as ve:
            return ve


class FakeWebSocket:
    """Uvicorn-side websocket stand-in for the firehose route.

    outbox holds frames the route has sent; the drainer consumes at
    the client's speed. A full outbox blocks send_text, which trips
    ConnectionManager's send timeout - the same pressure a real slow
    TCP peer applies.
    """

    def __init__(
        self,
        app: Any,
        *,
        buffer_size: int = 1000,
        name: str = "ws",
        api_key: str | None = None,
        force_anonymous: bool = True,
    ):
        self.app = app
        self.name = name
        self.outbox: asyncio.Queue[str] = asyncio.Queue(maxsize=buffer_size)
        self.query_params: dict[str, str] = (
            {"anonymous": "1"} if force_anonymous else {}
        )
        self.headers: dict[str, str] = {"x-api-key": api_key} if api_key else {}
        self.close_frame: dict[str, Any] | None = None
        self.sent_count = 0
        self._connect_delivered = False
        self._closed = asyncio.Event()

    async def accept(self) -> None:
        return None

    async def send_text(self, data: str) -> None:
        await self.outbox.put(data)
        self.sent_count += 1

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        if self.close_frame is None:
            self.close_frame = {"code": code, "reason": reason or ""}
            self._closed.set()

    async def receive(self) -> dict[str, Any]:
        if not self._connect_delivered:
            self._connect_delivered = True
            return {"type": "websocket.connect"}
        await self._closed.wait()
        code = self.close_frame["code"] if self.close_frame else 1000
        return {"type": "websocket.disconnect", "code": code}


class FirehoseScenarioConfig(BaseModel):
    duration_s: float = Field(default=60.0, gt=0.0)
    feed_rate_s: int = Field(default=500, gt=0)
    pool_size: int = Field(default=200, ge=1)
    payload_seed: int = 42
    kafka_seed: int = 42
    machine_seed: int = 7
    error_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    poison_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    parse_cost_s: float = Field(default=0.0, ge=0.0)
    n_clients: int = Field(default=5, ge=1)
    n_slow_clients: int = Field(default=0, ge=0)
    client_slow_s: float = Field(default=0.0, ge=0.0)
    client_buffer: int = Field(default=1000, gt=0)
    kick_grace_s: float = Field(default=30.0, gt=0.0)
    # broker outage window: get_one fails with a broker_down error for
    # [outage_at_s, outage_at_s + outage_duration_s), exercising the
    # pump's backoff path against a prolonged outage
    outage_at_s: float = Field(default=0.0, ge=0.0)
    outage_duration_s: float = Field(default=0.0, ge=0.0)


class FirehoseClientReport(BaseModel):
    name: str
    received: int
    sent: int
    close_code: int | None
    close_reason: str


class FirehoseReport(BaseModel):
    config: FirehoseScenarioConfig
    duration_s: float
    produced: int
    consumed: int
    backlog: int
    messages_delivered: int
    kicked: int
    dropped: int
    connections_left: int
    clients: list[FirehoseClientReport]


_GROUPS: dict[str, FakeKafka] = {}


def _make_consumer_patch(
    machine: Machine,
    kafka_config: KafkaConfig,
    pool: list[bytes] | None = None,
    *,
    payload_factory: "Callable[[int], bytes] | None" = None,
) -> Callable[..., Any]:
    """Build the QueueRepo.create_consumer replacement.

    One FakeKafka per (topic, consumer group). Payloads come either
    from a pre-built pool (cycled by offset) or from a factory called
    per offset at production time.
    """
    if payload_factory is None:
        if pool is None:
            raise ValueError("need pool or payload_factory")
        payload_factory = lambda offset: pool[offset % len(pool)]  # noqa: E731

    def create_consumer(self: QueueRepo, user: Any, topic: str) -> Any:
        group = self.resolve_consumer_group(user=user, topic=topic)
        if group not in _GROUPS:
            _GROUPS[group] = FakeKafka(
                machine, kafka_config, payload_factory=payload_factory
            )
        return FakeKafkaQueueConsumer(_GROUPS[group], model=TOPIC_MODELS[topic])

    return create_consumer


async def _drain(websocket: FakeWebSocket, slow_s: float, received: list[int]) -> None:
    """Model the peer reading frames at its own speed.

    Exits when the route closes the socket; slow_s pauses between
    frames are the slow-client scenario (virtual time).
    """
    while websocket.close_frame is None:
        get_task = asyncio.create_task(websocket.outbox.get())
        closed_task = asyncio.create_task(websocket._closed.wait())
        done, pending = await asyncio.wait(
            {get_task, closed_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        if closed_task in done:
            return
        received[0] += 1
        if slow_s > 0.0:
            await asyncio.sleep(slow_s)


def _counter(name: str, labels: dict[str, str]) -> float:
    value = REGISTRY.get_sample_value(name, labels)
    return 0.0 if value is None else value


async def main(**kwargs) -> FirehoseReport:
    """Run the real firehose (pump + exchange + routes) on the clock."""
    config = FirehoseScenarioConfig(**kwargs)
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
            parse_cost_s=config.parse_cost_s,
            faults=KafkaFaults(
                error_pct=config.error_pct, poison_pct=config.poison_pct
            ),
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
        labels = {"topic": TOPIC, "type": "anonymous"}
        baseline = {
            "messages": _counter("firehose_messages_total", labels),
            "kicked": _counter("firehose_kicked_total", labels),
            "dropped": _counter("firehose_dropped_total", labels),
        }

        sockets: list[FakeWebSocket] = []
        routes: list[asyncio.Task[Any]] = []
        received: list[list[int]] = []
        for i in range(config.n_clients):
            websocket = FakeWebSocket(
                app, buffer_size=config.client_buffer, name=f"client-{i}"
            )
            counts: list[int] = [0]
            sockets.append(websocket)
            received.append(counts)
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
                _drain(
                    websocket,
                    config.client_slow_s if i < config.n_slow_clients else 0.0,
                    counts,
                ),
                name=f"drain-{i}",
            )

        if config.outage_duration_s > 0.0 and config.outage_at_s > 0.0:

            async def broker_outage() -> None:
                await asyncio.sleep(config.outage_at_s)
                for kafka in _GROUPS.values():
                    kafka.set_down(True)
                await asyncio.sleep(config.outage_duration_s)
                for kafka in _GROUPS.values():
                    kafka.set_down(False)

            asyncio.create_task(broker_outage(), name="broker-outage")

        await asyncio.sleep(config.duration_s)

        # wind down: close sockets so routes clean up (unsubscribe,
        # release), then stop the feeds so no timers remain
        for websocket in sockets:
            await websocket.close(code=1000, reason="scenario end")
        await asyncio.gather(*routes, return_exceptions=True)
        for kafka in _GROUPS.values():
            await kafka.stop()

        state.queue_manager._queues.clear()
        clients = [
            FirehoseClientReport(
                name=ws.name,
                received=counts[0],
                sent=ws.sent_count,
                close_code=(ws.close_frame["code"] if ws.close_frame else None),
                close_reason=(ws.close_frame["reason"] if ws.close_frame else ""),
            )
            for ws, counts in zip(sockets, received, strict=True)
        ]
        feed = next(iter(_GROUPS.values()), None)
        return FirehoseReport(
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
            connections_left=state.connection_manager.count(
                group=f"fh-anonymous-{TOPIC}"
            ),
            clients=clients,
        )
