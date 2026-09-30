"""Fake Kafka consumer mimicking AIOKafkaConsumerAdapter's per-message path.

Consumers block on get_one() like aiokafka's getone(). The "broker" side
pre-generates raw JSON payloads (payloads.py, seeded) and a producer task
feeds them at a fixed rate, so the pump's cost profile (deserialize +
validate + fanout) matches the real kafka adapter.

Faults are injected per consumed message from a seeded percentage
schedule (events.py), so a run replays by passing the same seed.
"""

import asyncio
import logging
import time
from typing import Type

import orjson
from bot_detector.event_queue.structs import ScrapedStruct
from prometheus_client import Gauge
from pydantic import BaseModel, ValidationError

from .events import EventInjector, EventSchedule
from .payloads import PayloadConfig, build_payload_pool

logger = logging.getLogger(__name__)

SIM_PRODUCED = Gauge(
    "sim_produced_total", "messages fed by the sim producer", ["group"]
)
SIM_CONSUMED = Gauge(
    "sim_consumed_total", "messages consumed from the sim feed", ["group"]
)
SIM_BACKLOG = Gauge("sim_backlog", "sim feed backlog (produced - consumed)", ["group"])


class FakeKafkaConsumer:
    """QueueConsumer-protocol stand-in backed by an in-process queue.

    events inject failure modes into the consumed stream (same path
    the real pump sees as values); both scale with the message rate
    and replay from the schedule's seed:

    - error_pct: RuntimeError("sim kafka error") - a transient consumer
      error the route skips with a 0.5s backoff
    - poison_pct: a ValidationError (malformed payload that fails
      model validation)
    """

    def __init__(
        self,
        topic: str,
        group: str,
        rate_s: int,
        payload_config: PayloadConfig,
        events: EventSchedule,
        model: Type[BaseModel] = ScrapedStruct,
    ):
        self.topic = topic
        self.group = group
        self.rate_s = rate_s
        self.model = model
        self._injector = EventInjector(events)
        self.errors_returned = 0
        self.poison_returned = 0
        self.produced_total = 0
        self.consumed_total = 0
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100_000)
        self._task: asyncio.Task | None = None
        self.created = time.monotonic()
        self._g_produced = SIM_PRODUCED.labels(group=group)
        self._g_consumed = SIM_CONSUMED.labels(group=group)
        self._g_backlog = SIM_BACKLOG.labels(group=group)
        self._pool = build_payload_pool(payload_config)

    @property
    def schedule(self) -> EventSchedule:
        return self._injector.schedule

    async def start(self) -> None:
        self._task = asyncio.create_task(
            self._produce(), name=f"sim-producer-{self.group}"
        )

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def get_one(self) -> BaseModel | Exception | None:
        # injected failures first: the pump/route see them as values,
        # exactly like transient kafka errors and poison payloads
        self.consumed_total += 1
        match self._injector.next_event():
            case "error":
                self.errors_returned += 1
                self._g_consumed.set(self.consumed_total)
                return RuntimeError("sim kafka error")
            case "poison":
                self.poison_returned += 1
                self._g_consumed.set(self.consumed_total)
                try:
                    return self.model.model_validate({"nope": True})
                except ValidationError as ve:
                    return ve
        raw = await self._queue.get()
        self._g_consumed.set(self.consumed_total)
        self._g_backlog.set(self.produced_total - self.consumed_total)
        # same path as AIOKafkaConsumerAdapter: value_deserializer then validate
        dct = orjson.loads(raw)
        try:
            return self.model.model_validate(dct)
        except ValidationError as ve:
            return ve

    async def _produce(self) -> None:
        # burst per tick to hit the target rate without per-message sleeps;
        # awaiting put applies backpressure instead of crashing at maxsize
        tick_s = 0.01
        per_tick = max(1, int(self.rate_s * tick_s))
        i = 0
        n = len(self._pool)
        while True:
            t0 = time.monotonic()
            for _ in range(per_tick):
                await self._queue.put(self._pool[i % n])
                i += 1
                self.produced_total += 1
            self._g_produced.set(self.produced_total)
            self._g_backlog.set(self.produced_total - self.consumed_total)
            elapsed = time.monotonic() - t0
            delay = tick_s - elapsed
            if delay > 0:
                await asyncio.sleep(delay)
