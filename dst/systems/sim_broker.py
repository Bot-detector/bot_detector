import asyncio
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TypeAlias

from aiokafka.errors import (
    ConsumerStoppedError,
    KafkaTimeoutError,
    ProducerClosed,
)
from pydantic import BaseModel, ConfigDict, Field

from dst.faults import KafkaFaultConfig, bucket, draw

from .sim_costs import CpuCosts, LinkCosts

PayloadFactory: TypeAlias = Callable[[str, int, int], bytes]
FeedPayloadFactory: TypeAlias = Callable[[int], bytes]

PRODUCE_STREAM = "k:p:{topic}:{partition}"
FETCH_STREAM = "k:c:{topic}:{group}:{partition}"

# feed pacing granularity: 10/s is one message every ten ticks, not
# one message per tick (fractional carry keeps sub-100/s rates honest)
TICK_S = 0.01

# the SimFeedKafka stream shape: one topic, one partition, one group
FEED_TOPIC = "feed"
FEED_PARTITION = 0
FEED_GROUP = "sim"


def _filler(offset: int, size: int) -> bytes:
    """Deterministic offset-derived filler bytes of exactly ``size``."""
    return (offset.to_bytes(8, "big") * (size // 8 + 1))[:size]


class SimBrokerError(Exception):
    """Injected kafka fault returned as a value, never raised.

    kind is ``"broker_error"`` (transient, retryable), ``"poison"``
    (malformed payload / protocol error) or ``"broker_down"``
    (scenario-driven outage).
    """

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(f"{kind}: {detail}")
        self.kind = kind


class SimBrokerConfig(BaseModel):
    """Broker knobs: run seed, fault table, payload size, feed shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    seed: int = 0
    faults: KafkaFaultConfig = Field(default_factory=KafkaFaultConfig)
    payload_bytes: int = Field(default=1024, ge=1)
    # paced feed: messages per virtual second; 0 disables the feed task
    feed_rate_s: int = Field(default=0, ge=0)
    # backlog bound: the feed task parks once lag reaches this
    max_backlog: int = Field(default=100_000, gt=0)
    # the broker has nothing to deliver until this much virtual time
    # has passed (a topic whose upstream starts releasing late)
    start_delay_s: float = Field(default=0.0, ge=0.0)


@dataclass(frozen=True, slots=True)
class SimMessage:
    """One consumed message; payload rendered lazily at fetch time."""

    topic: str
    partition: int
    offset: int
    payload: bytes


class SimBroker:
    """Partitioned log core with counter-based faults.

    Topics/partitions materialize on first use. Payload bytes are
    stored only when produced eagerly (``produce`` called with actual
    payloads, as the feed task does — a feed-rendered payload must be
    the bytes that existed at arrival time, and they serve exactly one
    consumer group); offset-produced payloads render on demand per
    (topic, partition, offset), so memory stays O(offsets) at
    millions of messages. Errors are returned as values, never raised.

    Draw order (fixed, counter-based via ``dst.faults``):
    - ``produce``: one draw per produced offset on
      ``"k:p:{topic}:{partition}"``:
      ``bucket(d, produce_buffer_timeout_pct, produce_closed_pct)``.
      The first faulted offset returns its error value and aborts the
      batch; already-appended offsets stay (partial produce, like a
      real accumulator raising mid-batch).
    - ``get_one``/``get_many``: one draw per fetch attempt on
      ``"k:c:{topic}:{group}:{partition}"``:
      ``bucket(d, fetch_timeout_pct, consumer_stopped_pct,
      poison_pct, slow_fetch_pct, error_pct)`` — slow is a latency,
      not a failure: it sleeps ``slow_fetch_s`` on the virtual clock
      then delivers. A faulted attempt returns the error value without
      advancing the cursor; ``get_many`` stops the batch there.
    - A drained partition returns ``KafkaTimeoutError`` without a draw
      (no fetch happened).

    Ordinals are per-surface attempt counters (produce per
    (topic, partition), fetch per (topic, group, partition)), so draws
    are pure functions of ``(seed, stream, attempt)`` and a run replays
    per seed. A retry redraws with the next attempt
    ordinal: transient faults never strand a cursor, unlike the
    previous cursor-keyed draws this consolidation replaces.

    The paced feed (``start_feed``) appends at ``feed_rate_s``
    messages per virtual second with fractional-carry pacing and
    parks itself while lag reaches ``max_backlog``.

    Deferred: commit/outage draws (outage is
    scenario-driven via ``SimFeedKafka.set_down``), consumer groups
    and rebalance machinery.
    """

    def __init__(
        self,
        config: SimBrokerConfig,
        *,
        payload_factory: PayloadFactory | None = None,
    ) -> None:
        self.config = config
        self._payload_factory: PayloadFactory = payload_factory or self._default_payload
        self._logs: dict[tuple[str, int], deque[int]] = {}
        self._high_watermarks: dict[tuple[str, int], int] = {}
        self._cursors: dict[tuple[str, str, int], int] = {}
        # payloads rendered at production time (feed/eager produce),
        # popped on delivery so memory tracks the live backlog
        self._eager_payloads: dict[tuple[str, int, int], bytes] = {}
        self._produce_attempts: dict[tuple[str, int], int] = {}
        self._fetch_attempts: dict[tuple[str, str, int], int] = {}
        self._feed_task: asyncio.Task[None] | None = None
        self._feed_started = False
        # eagerly produced bytes serve exactly one consumer group; the
        # first group to deliver claims it (asserted at the read surface)
        self._eager_group: str | None = None
        self.produced_total = 0
        self.consumed_total = 0
        self.feed_faults = 0

    def high_watermark(self, topic: str, partition: int) -> int:
        """Next offset the partition will hand out; 0 before first use."""
        return self._high_watermarks.get((topic, partition), 0)

    def lag(self, topic: str, partition: int, group: str) -> int:
        """Messages produced but not yet consumed by the group."""
        cursor = self._cursor(topic, group, partition)
        return self.high_watermark(topic, partition) - cursor

    @property
    def feed_running(self) -> bool:
        """True while the paced feed task is alive (started, not stopped)."""
        task = self._feed_task
        return task is not None and not task.done()

    @property
    def feed_started(self) -> bool:
        """True once ``start_feed`` has been called (even if since stopped)."""
        return self._feed_started

    async def produce(
        self,
        topic: str,
        partition: int,
        payloads: bytes | Iterable[bytes] | int,
    ) -> Exception | None:
        """Append payloads (or range-fill ``int`` count) to the log.

        Args:
            topic: Topic name, created on first use.
            partition: Partition index, created on first use.
            payloads: One payload, an iterable of payloads (stored
                eagerly: the delivered bytes equal the produced
                bytes), or a count of offset-derived filler payloads
                to range-fill (rendered lazily at fetch time).

        Returns:
            ``None`` on success, or the fault error value from the
            first faulted offset (batch aborted there, partial append).
        """
        items: Iterable[bytes | None]
        eager = False
        if isinstance(payloads, bytes):
            items = (payloads,)
            eager = True
        elif isinstance(payloads, int):
            count = payloads
            items = iter(()) if count <= 0 else (None for _ in range(count))
        else:
            items = payloads
            eager = True
        log = self._partition(topic, partition)
        offset = self.high_watermark(topic, partition)
        stream = PRODUCE_STREAM.format(topic=topic, partition=partition)
        for payload in items:
            outcome = self._produce_outcome(topic, partition, stream)
            if outcome == 0:
                return KafkaTimeoutError()
            if outcome == 1:
                return ProducerClosed()
            log.append(offset)
            if eager and payload is not None:
                self._eager_payloads[(topic, partition, offset)] = payload
            offset += 1
            self._high_watermarks[(topic, partition)] = offset
            self.produced_total += 1
        return None

    def _check_eager_group(self, group: str) -> None:
        """Eagerly produced bytes serve exactly one consumer group.

        A feed-rendered payload must be the bytes that existed at
        arrival time; they are popped on first delivery, so a second
        group reading the same offsets would silently get filler.
        """
        assert self._eager_group in (None, group), (
            f"eager produce supports exactly one consumer group: "
            f"{self._eager_group!r} claimed the log, {group!r} reads it too"
        )

    async def get_one(
        self,
        topic: str,
        partition: int,
        group: str,
    ) -> SimMessage | Exception:
        """Consume one message at the group cursor, or a fault value."""
        self._check_eager_group(group)
        hw = self.high_watermark(topic, partition)
        cursor = self._cursor(topic, group, partition)
        if cursor >= hw:
            return KafkaTimeoutError(f"{topic}[{partition}] drained at {cursor}")
        outcome = await self._fetch_outcome(topic, group, partition)
        if outcome is not None:
            return outcome
        return self._deliver(group, topic, partition, cursor)

    async def get_many(
        self,
        topic: str,
        partition: int,
        group: str,
        count: int,
    ) -> list[SimMessage | Exception]:
        """Consume up to ``count`` messages with no unconditional
        sleep per message.

        Stops early on a fetch fault (appended as the last list entry)
        or when the partition is drained; the list may be shorter than
        ``count`` or empty.
        """
        self._check_eager_group(group)
        results: list[SimMessage | Exception] = []
        while len(results) < max(count, 0):
            cursor = self._cursor(topic, group, partition)
            if cursor >= self.high_watermark(topic, partition):
                break
            outcome = await self._fetch_outcome(topic, group, partition)
            if outcome is not None:
                results.append(outcome)
                break
            results.append(self._deliver(group, topic, partition, cursor))
        return results

    async def start_feed(
        self,
        topic: str,
        partition: int,
        group: str,
        *,
        payload_factory: FeedPayloadFactory | None = None,
    ) -> None:
        """Start the paced producer task for one partition.

        The feed appends ``feed_rate_s`` messages per virtual second
        (fractional carry, :data:`TICK_S` granularity), rendering each
        payload at production time via ``payload_factory(offset)``
        (offset = the log offset it will land at). It parks while lag
        reaches ``max_backlog`` so the backlog stays bounded. No-op
        when already running or ``feed_rate_s`` is 0.
        """
        if self._feed_task is not None or self.config.feed_rate_s <= 0:
            return
        factory = payload_factory or self._default_feed_payload
        self._feed_started = True
        self._feed_task = asyncio.create_task(
            self._feed_loop(topic, partition, group, factory),
            name="sim-kafka-producer",
        )

    async def stop_feed(self) -> None:
        """Cancel the paced producer task, if running."""
        task = self._feed_task
        if task is not None:
            self._feed_task = None
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _feed_loop(
        self,
        topic: str,
        partition: int,
        group: str,
        payload_factory: FeedPayloadFactory,
    ) -> None:
        """Produce at ``feed_rate_s`` msg/s; parks at the backlog bound.

        Runs until ``stop_feed`` cancels the task; the backlog park is
        the feed's backpressure (a consumer must drain, or the feed
        holds at ``max_backlog`` exactly like the retired bounded
        queue did).
        """
        if self.config.start_delay_s > 0.0:
            await asyncio.sleep(self.config.start_delay_s)
        carry = 0.0
        while True:  # service task: exits via stop_feed's cancel
            carry += self.config.feed_rate_s * TICK_S
            count = int(carry)
            carry -= count
            if count > 0:
                while self.lag(topic, partition, group) >= self.config.max_backlog:
                    await asyncio.sleep(TICK_S)
                hw = self.high_watermark(topic, partition)
                error = await self.produce(
                    topic,
                    partition,
                    [payload_factory(hw + i) for i in range(count)],
                )
                if error is not None:
                    # faulted feed produce: the aborted tail is dropped
                    # (counted, never silent); pacing resumes next tick
                    self.feed_faults += 1
            await asyncio.sleep(TICK_S)

    def _partition(self, topic: str, partition: int) -> deque[int]:
        key = (topic, partition)
        log = self._logs.get(key)
        if log is None:
            log = deque()
            self._logs[key] = log
        return log

    def _cursor(self, topic: str, group: str, partition: int) -> int:
        return self._cursors.get((topic, group, partition), 0)

    def _produce_outcome(self, topic: str, partition: int, stream: str) -> int:
        """Resolve one produce attempt against the produce buckets."""
        faults = self.config.faults
        key = (topic, partition)
        ordinal = self._produce_attempts.get(key, 0)
        self._produce_attempts[key] = ordinal + 1
        return bucket(
            draw(self.config.seed, stream, ordinal),
            faults.produce_buffer_timeout_pct,
            faults.produce_closed_pct,
        )

    async def _fetch_outcome(
        self,
        topic: str,
        group: str,
        partition: int,
    ) -> Exception | None:
        """Resolve one fetch attempt against the fixed fetch buckets.

        Bucket order (documented in :class:`KafkaFaultConfig`):
        timeout -> consumer stopped -> poison -> slow -> error. Slow
        sleeps ``slow_fetch_s`` on the virtual clock and delivers.
        """
        faults = self.config.faults
        key = (topic, group, partition)
        ordinal = self._fetch_attempts.get(key, 0)
        self._fetch_attempts[key] = ordinal + 1
        outcome = bucket(
            draw(
                self.config.seed,
                FETCH_STREAM.format(topic=topic, group=group, partition=partition),
                ordinal,
            ),
            faults.fetch_timeout_pct,
            faults.consumer_stopped_pct,
            faults.poison_pct,
            faults.slow_fetch_pct,
            faults.error_pct,
        )
        if outcome == 0:
            return KafkaTimeoutError(f"fetch timeout at attempt {ordinal}")
        if outcome == 1:
            return ConsumerStoppedError()
        if outcome == 2:
            return SimBrokerError("poison", "sim malformed payload")
        if outcome == 3:
            await asyncio.sleep(faults.slow_fetch_s)
        elif outcome == 4:
            return SimBrokerError(
                "broker_error", "sim transient broker error (retryable)"
            )
        return None

    def _deliver(
        self,
        group: str,
        topic: str,
        partition: int,
        cursor: int,
    ) -> SimMessage:
        self._cursors[(topic, group, partition)] = cursor + 1
        self.consumed_total += 1
        key = (topic, partition, cursor)
        eager = self._eager_payloads.pop(key, None)
        if eager is not None and self._eager_group is None:
            self._eager_group = group
        return SimMessage(
            topic=topic,
            partition=partition,
            offset=cursor,
            payload=(
                eager
                if eager is not None
                else self._payload_factory(topic, partition, cursor)
            ),
        )

    def _default_feed_payload(self, offset: int) -> bytes:
        return _filler(offset, self.config.payload_bytes)

    def _default_payload(self, topic: str, partition: int, offset: int) -> bytes:
        return _filler(offset, self.config.payload_bytes)


class KafkaConfig(BaseModel):
    """Feed shape, consumer link costs and fault table for one paced
    SimBroker stream (the scenario-level kafka stand-in config; the
    link knobs are fake-owned, replacing the retired Machine network
    model)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    seed: int = 0
    feed_rate_s: int = Field(default=1000, gt=0)
    payload_bytes: int = Field(default=1024, ge=1)
    parse_cost_s: float = Field(default=0.0, ge=0.0)
    # consumer link: one fetch per consumed message. Latency is
    # mean_ms + uniform(-jitter_ms, +jitter_ms) clamped at zero, drawn
    # counter-based per attempt on dedicated streams; bandwidth_mbps
    # (when set) adds payload transfer time; fetch_loss_pct is the
    # seeded transient-loss roll (a LinkError value per lost fetch).
    fetch_mean_ms: float = Field(default=0.01, ge=0.0)
    fetch_jitter_ms: float = Field(default=0.005, ge=0.0)
    bandwidth_mbps: float | None = Field(default=None, gt=0.0)
    fetch_loss_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    max_backlog: int = Field(default=100_000, gt=0)
    start_delay_s: float = Field(default=0.0, ge=0.0)
    faults: KafkaFaultConfig = Field(default_factory=KafkaFaultConfig)


class SimFeedKafka:
    """Kafka-shaped single-stream surface over one SimBroker partition.

    The broker owns the log, the paced feed task and the counter-based
    fault draws; this adapter owns the per-message costs
    the scenarios model on top — one link fetch plus one cpu parse per
    consumed message (:class:`LinkCosts` / :class:`CpuCosts`, drawn on
    dedicated fault streams), and the scenario-driven outage
    (:meth:`set_down`). When the consumer outruns the feed it parks on
    the virtual clock until the next arrival, so a consumer with a
    slow parse path visibly falls behind the feed.

    Errors are always returned as values (never raised), matching how
    transient kafka errors, seeded link loss and poison payloads reach
    the real pump. ``link`` and ``cpu`` carry the cost counters.
    """

    #: fault streams for the fake-owned consumer costs (one topic, one
    #: partition, one group, so a fixed stream name replays per seed)
    NET_STREAM = "k:net:sim:0"

    def __init__(
        self,
        config: KafkaConfig,
        *,
        payload_factory: FeedPayloadFactory | None = None,
    ):
        self.config = config
        self._payload_factory = payload_factory
        self.link = LinkCosts(
            seed=config.seed,
            stream=self.NET_STREAM,
            mean_ms=config.fetch_mean_ms,
            jitter_ms=config.fetch_jitter_ms,
            bandwidth_mbps=config.bandwidth_mbps,
            loss_pct=config.fetch_loss_pct,
        )
        self.cpu = CpuCosts()
        self._broker = SimBroker(
            SimBrokerConfig(
                seed=config.seed,
                faults=config.faults,
                payload_bytes=config.payload_bytes,
                feed_rate_s=config.feed_rate_s,
                max_backlog=config.max_backlog,
                start_delay_s=config.start_delay_s,
            )
        )
        self._down = False

    @property
    def backlog(self) -> int:
        """Broker-retained surplus: produced minus consumed."""
        return self._broker.lag(FEED_TOPIC, FEED_PARTITION, FEED_GROUP)

    @property
    def produced_total(self) -> int:
        return self._broker.produced_total

    @property
    def consumed_total(self) -> int:
        return self._broker.consumed_total

    def set_down(self, down: bool) -> None:
        """Simulate a broker outage: get_one fails until set back up.

        Mirrors a real broker connection error surfacing as a value
        from the consumer, so the pump runs its backoff path for the
        whole window. Arrivals keep queueing: nothing is lost.
        """
        self._down = down

    async def start(self) -> None:
        """Start the paced feed on the underlying broker."""
        await self._broker.start_feed(
            FEED_TOPIC,
            FEED_PARTITION,
            FEED_GROUP,
            payload_factory=self._payload_factory,
        )

    async def stop(self) -> None:
        """Stop the paced feed."""
        await self._broker.stop_feed()

    async def get_one(self) -> SimMessage | Exception:
        """Consume one message or an injected fault (as a value).

        Per call: fake-owned costs (link fetch, cpu parse), a parked
        wait while the feed is behind, then the broker's fixed-order
        draw. A faulted attempt costs the fetch and redraws on retry,
        so the stream recovers like a real consumer's backoff loop.
        """
        if self._down:
            return SimBrokerError("broker_down", "sim broker outage")
        error = await self.link.fetch(n_bytes=self.config.payload_bytes)
        if error is not None:
            return error
        if self.config.parse_cost_s > 0.0:
            await self.cpu.work(self.config.parse_cost_s)
        # park until the paced feed arrives. Once the feed has stopped
        # and the log is drained there is nothing to wait for: return
        # the drained error instead of spinning (a parked loop keeps
        # the virtual loop non-idle and would defeat DSTIdleError)
        while self._broker.lag(FEED_TOPIC, FEED_PARTITION, FEED_GROUP) <= 0:
            if self._broker.feed_started and not self._broker.feed_running:
                return KafkaTimeoutError(
                    f"{FEED_TOPIC}[{FEED_PARTITION}] drained: feed stopped"
                )
            await asyncio.sleep(TICK_S)
        return await self._broker.get_one(FEED_TOPIC, FEED_PARTITION, FEED_GROUP)
