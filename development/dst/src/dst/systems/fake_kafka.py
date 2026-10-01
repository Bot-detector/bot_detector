"""Fake Kafka: a rate-controlled message feed on the virtual timeline.

Port of perf's ``FakeKafkaConsumer`` concepts, rebuilt on DST so the
feed, the costs and the faults all run on the virtual clock:

- A producer task feeds payloads at ``rate_s`` messages per virtual
  second into a bounded queue; backlog (produced - consumed) is the
  broker-retained surplus a real kafka would keep.
- ``get_one()`` is the consumer surface (QueueConsumer-protocol
  shaped): each call pays machine costs for the message — an io fetch
  against a named io system plus a cpu parse cost — so a consumer
  with a slow parse path visibly falls behind the feed.
- Faults are drawn per consumed message from one seeded RNG in a
  fixed order (error -> poison -> slow), so a run replays per seed:
  - ``error_pct``: transient broker error (retryable, values not
    raises) — the consumer's backoff path.
  - ``poison_pct``: malformed payload — the application/protocol
    error path; the fake returns a typed ``FakeKafkaError`` with
    ``kind="poison"`` (a real adapter maps this to the model's
    ValidationError).
  - ``slow_pct``: slow fetch; timeouts stay app policy — the consumer
    ``wait_for``s and gets its TimeoutError.

Errors are always returned as values (never raised), matching how
transient kafka errors and poison payloads reach the real pump.
"""

import asyncio
import random
from collections.abc import Callable

from pydantic import BaseModel, Field

from ..machine import VirtualMachine

TICK_S = 0.01


class KafkaFaults(BaseModel):
    """Percentage-based fault draws per consumed message."""

    error_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    poison_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    slow_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    slow_s: float = Field(default=1.0, ge=0.0)


class KafkaConfig(BaseModel):
    """Feed shape, message size, consumer cost and fault schedule."""

    seed: int = 0
    rate_s: int = Field(default=1000, gt=0)
    payload_bytes: int = Field(default=1024, ge=1)
    parse_cost_s: float = Field(default=0.0, ge=0.0)
    max_queue: int = Field(default=100_000, gt=0)
    start_delay_s: float = Field(default=0.0, ge=0.0)
    faults: KafkaFaults = Field(default_factory=KafkaFaults)


class KafkaMessage(BaseModel):
    """One consumed message; payload is deterministic filler bytes."""

    offset: int
    payload: bytes


class FakeKafkaError(Exception):
    """Injected kafka fault returned as a value.

    kind is "broker_error" (transient, retryable) or "poison"
    (malformed payload / protocol error).
    """

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(f"{kind}: {detail}")
        self.kind = kind


class FakeKafka:
    """Rate-controlled broker stand-in with seeded fault injection.

    Binds to a VirtualMachine for message costs (io fetch + cpu
    parse). The io system must exist in the machine's config; unknown
    systems are construction-time configuration errors, not surprises
    mid-scenario.
    """

    def __init__(
        self,
        machine: VirtualMachine,
        config: KafkaConfig,
        *,
        io_system: str = "kafka",
        payload_factory: Callable[[int], bytes] | None = None,
    ):
        if io_system not in machine.config.io:
            raise ValueError(
                f"io system {io_system!r} not in machine config; "
                f"configured: {sorted(machine.config.io)}"
            )
        if config.faults.error_pct + config.faults.poison_pct > 100.0:
            raise ValueError(
                f"error_pct + poison_pct must be <= 100, got "
                f"{config.faults.error_pct} + {config.faults.poison_pct}"
            )
        self.machine = machine
        self.config = config
        self.io_system = io_system
        self._payload_factory = payload_factory or self._default_payload
        self._rng = random.Random(config.seed)
        self._queue: asyncio.Queue[tuple[int, bytes]] = asyncio.Queue(
            maxsize=config.max_queue
        )
        self._producer: asyncio.Task[None] | None = None
        self._down = False
        self.produced_total = 0
        self.consumed_total = 0
        self.errors_returned = 0
        self.poisons_returned = 0
        self.slows_hit = 0

    @property
    def backlog(self) -> int:
        """Broker-retained surplus: produced minus consumed."""
        return max(0, self.produced_total - self.consumed_total)

    def set_down(self, down: bool) -> None:
        """Simulate a broker outage: get_one fails until set back up.

        Mirrors a real broker connection error surfacing as a value from
        the consumer, so the pump runs its backoff path for the whole
        window. Arrivals keep queueing: nothing is lost.
        """
        self._down = down

    async def start(self) -> None:
        if self._producer is None:
            self._producer = asyncio.create_task(
                self._produce(), name="sim-kafka-producer"
            )

    async def stop(self) -> None:
        if self._producer is not None:
            self._producer.cancel()
            try:
                await self._producer
            except asyncio.CancelledError:
                pass
            self._producer = None

    async def get_one(self) -> KafkaMessage | Exception:
        """Consume one message or an injected fault (as a value).

        Draw order per call is fixed for replayability: broker error,
        poison, slow fetch, then the real message path (io fetch,
        cpu parse, queue handoff).
        """
        if self._down:
            return FakeKafkaError("broker_down", "sim broker outage")
        self.consumed_total += 1
        roll = self._rng.random() * 100.0
        faults = self.config.faults
        if roll < faults.error_pct:
            self.errors_returned += 1
            return FakeKafkaError(
                "broker_error", "sim transient broker error (retryable)"
            )
        if roll < faults.error_pct + faults.poison_pct:
            self.poisons_returned += 1
            return FakeKafkaError("poison", "sim malformed payload")
        if roll < faults.error_pct + faults.poison_pct + faults.slow_pct:
            self.slows_hit += 1
            await asyncio.sleep(faults.slow_s)

        io = await self.machine.io(self.io_system, n_bytes=self.config.payload_bytes)
        if io.error is not None:
            return io.error
        if self.config.parse_cost_s > 0.0:
            await self.machine.cpu(self.config.parse_cost_s, what="kafka-parse")
        offset, payload = await self._queue.get()
        return KafkaMessage(offset=offset, payload=payload)

    def _default_payload(self, offset: int) -> bytes:
        return (offset.to_bytes(8, "big") * (self.config.payload_bytes // 8 + 1))[
            : self.config.payload_bytes
        ]

    async def _produce(self) -> None:
        if self.config.start_delay_s > 0.0:
            # the broker has nothing to deliver yet (e.g. a topic whose
            # upstream only starts releasing after a window)
            await asyncio.sleep(self.config.start_delay_s)
        # fractional carry keeps rates below 100/s accurate: 10/s is
        # one message every ten ticks, not one message per tick
        carry = 0.0
        offset = 0
        while True:
            carry += self.config.rate_s * TICK_S
            count = int(carry)
            carry -= count
            for _ in range(count):
                await self._queue.put((offset, self._payload_factory(offset)))
                offset += 1
                self.produced_total += 1
            await asyncio.sleep(TICK_S)
