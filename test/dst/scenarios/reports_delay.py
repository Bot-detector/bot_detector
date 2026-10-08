"""reports.to_insert scenario: a 2h-delayed topic over a full day.

Runs the real firehose (pump, DelayAdapter, exchange, routes) for 24
simulated hours at 10 msg/s. The broker produces fresh messages from
t=0, each ts generated on the spot and jittered 0..300s into the past
(never sequential, never in the future).

The flow is the production mechanism itself:

1. the pump consumes the first message and the DelayAdapter locks on
   it - that hold sleep is what advances virtual time by ~2h
2. the adapter releases it, and the backlog plus the live feed yield
   in emission order (eventqueue -> kafka -> pump -> yield) from then
   on, pacing the stream 2h behind arrivals
3. at the end of the window the last ~2h of arrivals are still in
   kafka: the broker backlog is the "2 hours of messages left"

The clock must start at an epoch value (--start) because the hold math
compares report.ts against time.time(); virtual_time patches it.

Documented command (about a minute of wall time for a simulated day):

uv run python -m dst.main dst.scenarios.reports_delay \\
    --start 2000000000 --json-pretty
"""

import asyncio
import logging
import os
import random
from collections.abc import Callable

os.environ.setdefault("BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("DATABASE_URL", "mysql+asyncmy://sim:sim@localhost/sim")

import orjson  # noqa: E402
from bot_detector.firehose.api.firehose import firehose as firehose_route  # noqa: E402
from bot_detector.firehose.app import queue_manager  # noqa: E402
from bot_detector.firehose.app.consumer.queue_repo import QueueRepo  # noqa: E402
from bot_detector.firehose.app.exchange.delay import DelayAdapter  # noqa: E402
from bot_detector.firehose.core.config import Settings  # noqa: E402
from bot_detector.firehose.core.server import create_app  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from dst import (  # noqa: E402
    Machine,
    MachineConfig,
    NetworkConfig,
    VirtualClock,
)
from dst import virtual_time  # noqa: E402
from dst.scenarios.firehose import (  # noqa: E402
    FakeWebSocket,
    _GROUPS,
    _make_consumer_patch,
)
from dst.systems import KafkaConfig, KafkaFaults  # noqa: E402

logger = logging.getLogger(__name__)

TOPIC = "reports.to_insert"


class ReportsDelayConfig(BaseModel):
    duration_s: float = Field(default=86400.0, gt=0.0)
    feed_rate_s: float = Field(default=10.0, gt=0.0)
    # the topic's emission delay; the product's TOPIC_HOLDS default for
    # reports.to_insert is 7200 and is left untouched - this value is
    # used for the report math only
    delay_s: float = Field(default=7200.0, ge=0.0)
    jitter_max_s: float = Field(default=300.0, ge=0.0)
    ts_base_s: int = Field(default=2_000_000_000, ge=0)
    kafka_seed: int = 42
    jitter_seed: int = 7
    machine_seed: int = 7
    client_buffer: int = Field(default=50_000, gt=0)
    kick_grace_s: float = Field(default=30.0, gt=0.0)


class ReportsDelayReport(BaseModel):
    config: ReportsDelayConfig
    duration_s: float
    produced: int
    consumed: int
    broker_backlog: int  # kafka-retained arrivals: the "2h left" at the end
    received: int
    first_received_s: float | None
    last_received_s: float | None
    first_ts_offset_s: float | None  # first delivered ts, relative to window
    last_ts_offset_s: float | None  # stream reached ~duration - delay
    unstreamed_s: float | None  # window end minus last delivered ts: the "2h left"
    unstreamed_hours: float | None
    expected_lag_s: float  # delay - jitter_max: earliest possible delivery


def _payload_factory(
    config: ReportsDelayConfig, clock: VirtualClock
) -> Callable[[int], bytes]:
    """Generate one fresh report on the spot at production time.

    ts = current virtual time - uniform(0, jitter_max): the timestamps
    are non-sequential, never in the future, and every message enters
    the delay window at arrival - the DelayAdapter does the holding.
    """
    rng = random.Random(config.jitter_seed)

    def build(offset: int) -> bytes:
        # the clock starts at ts_base_s (runner start_s), so time()
        # already is the epoch; jitter only reaches into the past
        ts = clock.time() - rng.uniform(0.0, config.jitter_max_s)
        message = {
            "metadata": {"version": 0, "source": "sim"},
            "report": {
                "reporter_id": offset,
                "reported_id": offset + 1,
                "ts": int(ts),
                "equipment": {},
            },
        }
        return orjson.dumps(message)

    return build


async def _record(
    websocket: FakeWebSocket, clock: VirtualClock, records: list[tuple[float, int]]
) -> None:
    """Drain frames, recording (virtual receive time, report.ts)."""
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
        payload = get_task.result()
        records.append((clock.time(), orjson.loads(payload)["report"]["ts"]))


async def main(**kwargs) -> ReportsDelayReport:
    """Run the delayed topic for duration_s of virtual time."""
    config = ReportsDelayConfig(**kwargs)
    with virtual_time():
        logging.getLogger("bot_detector").setLevel(logging.WARNING)
        # the product hardcodes a 2h adapter for this topic; scaled runs
        # need a matching delay, so set ours and restore on the way out
        original_hold = queue_manager.TOPIC_HOLDS.get(TOPIC)
        queue_manager.TOPIC_HOLDS[TOPIC] = DelayAdapter(delay_s=config.delay_s)
        try:
            return await _run(config)
        finally:
            if original_hold is None:
                queue_manager.TOPIC_HOLDS.pop(TOPIC, None)
            else:
                queue_manager.TOPIC_HOLDS[TOPIC] = original_hold


async def _run(config: ReportsDelayConfig) -> ReportsDelayReport:
    machine = Machine(
        MachineConfig(
            seed=config.machine_seed,
            network=NetworkConfig(mean_ms=0.01, jitter_ms=0.005),
        )
    )
    kafka_config = KafkaConfig(
        seed=config.kafka_seed,
        rate_s=int(config.feed_rate_s),
        faults=KafkaFaults(),
    )
    _GROUPS.clear()
    QueueRepo.create_consumer = _make_consumer_patch(  # type: ignore[assignment]
        machine,
        kafka_config,
        payload_factory=_payload_factory(config, machine.clock),
    )
    app = create_app(Settings(port=0, metrics_port=0, kick_grace_s=config.kick_grace_s))

    websocket = FakeWebSocket(app, buffer_size=config.client_buffer, name="client-0")
    records: list[tuple[float, int]] = []
    route = asyncio.create_task(
        firehose_route(
            websocket=websocket,  # type: ignore[arg-type]
            topic=TOPIC,
        ),
        name="route-0",
    )
    drainer = asyncio.create_task(
        _record(websocket, machine.clock, records), name="drain-0"
    )

    await asyncio.sleep(config.duration_s)

    await websocket.close(code=1000, reason="scenario end")
    await asyncio.gather(route, drainer, return_exceptions=True)
    for kafka in _GROUPS.values():
        await kafka.stop()

    feed = next(iter(_GROUPS.values()), None)
    receive_times = [t for t, _ts in records]
    ts_offsets = [ts - config.ts_base_s for _t, ts in records]
    streamed_until = max(ts_offsets) if ts_offsets else None
    unstreamed = (
        config.duration_s - streamed_until if streamed_until is not None else None
    )
    return ReportsDelayReport(
        config=config,
        duration_s=config.duration_s,
        produced=feed.produced_total if feed else 0,
        consumed=feed.consumed_total if feed else 0,
        broker_backlog=feed.backlog if feed else 0,
        received=len(records),
        first_received_s=receive_times[0] if receive_times else None,
        last_received_s=receive_times[-1] if receive_times else None,
        first_ts_offset_s=ts_offsets[0] if ts_offsets else None,
        last_ts_offset_s=ts_offsets[-1] if ts_offsets else None,
        unstreamed_s=unstreamed,
        unstreamed_hours=unstreamed / 3600.0 if unstreamed is not None else None,
        expected_lag_s=config.delay_s - config.jitter_max_s,
    )
