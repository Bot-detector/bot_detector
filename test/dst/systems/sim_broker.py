"""SimBroker: partitioned kafka broker, lazy payloads, seeded faults."""

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

PayloadFactory: TypeAlias = Callable[[str, int, int], bytes]

PRODUCE_STREAM = "k:p:{topic}:{partition}"
FETCH_STREAM = "k:c:{group}:{partition}"


class SimBrokerConfig(BaseModel):
    """Broker knobs: run seed, fault table, rendered payload size."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    seed: int = 0
    faults: KafkaFaultConfig = Field(default_factory=KafkaFaultConfig)
    payload_bytes: int = Field(default=1024, ge=1)


@dataclass(frozen=True, slots=True)
class SimMessage:
    """One consumed message; payload rendered lazily at fetch time."""

    topic: str
    partition: int
    offset: int
    payload: bytes


class SimBroker:
    """Partitioned log core with counter-based faults (spec §5.1, B1+B2).

    Topics/partitions materialize on first use. Payload bytes are never
    stored at produce time — they render on demand per (topic,
    partition, offset), so memory stays O(offsets) at millions of
    messages (spec §4.5). Errors are returned as values, never raised.

    Draw order (fixed, counter-based via ``dst.faults``):
    - ``produce``: one draw per produced offset (ordinal = offset) on
      ``"k:p:{topic}:{partition}"``:
      ``bucket(d, produce_buffer_timeout_pct, produce_closed_pct)``.
      The first faulted offset returns its error value and aborts the
      batch; already-appended offsets stay (partial produce, like a
      real accumulator raising mid-batch).
    - ``get_one``/``get_many``: one draw per fetched position (ordinal
      = cursor) on ``"k:c:{group}:{partition}"``:
      ``bucket(d, fetch_timeout_pct, consumer_stopped_pct)``. The error
      value is returned without advancing the cursor (the message stays
      queued for the retry); ``get_many`` stops the batch there.
    - A drained partition returns ``KafkaTimeoutError`` without a draw
      (no fetch happened).

    Because draws are pure functions of ``(seed, stream, ordinal)``, a
    faulted ordinal is sticky: retrying the same offset/cursor redraws
    the identical outcome (spec §4.1 determinism over retry realism).

    Deferred (spec B3+): poison/slow/commit/outage wiring, consumer
    groups and rebalance machinery.
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
        self._cursors: dict[tuple[str, int], int] = {}
        self.produced_total = 0
        self.consumed_total = 0

    def high_watermark(self, topic: str, partition: int) -> int:
        """Next offset the partition will hand out; 0 before first use."""
        return self._high_watermarks.get((topic, partition), 0)

    def lag(self, topic: str, partition: int, group: str) -> int:
        """Messages produced but not yet consumed by the group."""
        cursor = self._cursors.get((group, partition), 0)
        return self.high_watermark(topic, partition) - cursor

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
            payloads: One payload, an iterable of payloads, or a count
                of offset-derived filler payloads to range-fill.

        Returns:
            ``None`` on success, or the fault error value from the
            first faulted offset (batch aborted there, partial append).
        """
        items: Iterable[bytes | None]
        if isinstance(payloads, bytes):
            items = (payloads,)
        elif isinstance(payloads, int):
            count = payloads
            items = iter(()) if count <= 0 else (None for _ in range(count))
        else:
            items = payloads
        log = self._partition(topic, partition)
        offset = self.high_watermark(topic, partition)
        stream = PRODUCE_STREAM.format(topic=topic, partition=partition)
        faults = self.config.faults
        for payload in items:
            outcome = bucket(
                draw(self.config.seed, stream, offset),
                faults.produce_buffer_timeout_pct,
                faults.produce_closed_pct,
            )
            if outcome == 0:
                return KafkaTimeoutError()
            if outcome == 1:
                return ProducerClosed()
            log.append(offset)
            offset += 1
            self._high_watermarks[(topic, partition)] = offset
            self.produced_total += 1
        return None

    async def get_one(
        self,
        topic: str,
        partition: int,
        group: str,
    ) -> SimMessage | Exception:
        """Consume one message at the group cursor, or a fault value."""
        hw = self.high_watermark(topic, partition)
        cursor = self._cursor(group, partition)
        if cursor >= hw:
            return KafkaTimeoutError(f"{topic}[{partition}] drained at {cursor}")
        outcome = self._fetch_outcome(group, partition, cursor)
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
        """Consume up to ``count`` messages with no per-message awaits.

        Stops early on a fetch fault (appended as the last list entry)
        or when the partition is drained; the list may be shorter than
        ``count`` or empty.
        """
        hw = self.high_watermark(topic, partition)
        cursor = self._cursor(group, partition)
        end = min(cursor + max(count, 0), hw)
        results: list[SimMessage | Exception] = []
        while cursor < end:
            outcome = self._fetch_outcome(group, partition, cursor)
            if outcome is not None:
                results.append(outcome)
                break
            results.append(self._deliver(group, topic, partition, cursor))
            cursor += 1
        return results

    def _partition(self, topic: str, partition: int) -> deque[int]:
        key = (topic, partition)
        log = self._logs.get(key)
        if log is None:
            log = deque()
            self._logs[key] = log
        return log

    def _cursor(self, group: str, partition: int) -> int:
        return self._cursors.get((group, partition), 0)

    def _fetch_outcome(
        self,
        group: str,
        partition: int,
        cursor: int,
    ) -> Exception | None:
        faults = self.config.faults
        outcome = bucket(
            draw(
                self.config.seed,
                FETCH_STREAM.format(group=group, partition=partition),
                cursor,
            ),
            faults.fetch_timeout_pct,
            faults.consumer_stopped_pct,
        )
        if outcome == 0:
            return KafkaTimeoutError(f"fetch timeout at cursor {cursor}")
        if outcome == 1:
            return ConsumerStoppedError()
        return None

    def _deliver(
        self,
        group: str,
        topic: str,
        partition: int,
        cursor: int,
    ) -> SimMessage:
        self._cursors[(group, partition)] = cursor + 1
        self.consumed_total += 1
        return SimMessage(
            topic=topic,
            partition=partition,
            offset=cursor,
            payload=self._payload_factory(topic, partition, cursor),
        )

    def _default_payload(self, topic: str, partition: int, offset: int) -> bytes:
        size = self.config.payload_bytes
        filler = offset.to_bytes(8, "big")
        return (filler * (size // 8 + 1))[:size]
