"""SimBroker: partitioned log, lazy payloads, seeded fault values."""

import asyncio
import time

from aiokafka.errors import (
    ConsumerStoppedError,
    KafkaTimeoutError,
    ProducerClosed,
)
from pydantic import ValidationError

from dst.faults import KafkaFaultConfig, bucket, draw
from dst.systems.sim_broker import SimBroker, SimBrokerConfig, SimMessage


def run(coro):
    return asyncio.run(coro)


def out_names(results) -> list[str]:
    return [type(r).__name__ for r in results]


def seed_with_bucket(stream: str, pcts: tuple[float, ...], want: int) -> int:
    for seed in range(10_000):
        if bucket(draw(seed, stream, 0), *pcts) == want:
            return seed
    raise AssertionError(f"no seed draws bucket {want} on {stream}")


def test_topics_and_partitions_materialize_on_first_use():
    async def scenario() -> tuple[int, int]:
        broker = SimBroker(SimBrokerConfig())
        await broker.produce("orders", 0, b"x")
        await broker.produce("orders", 2, b"y")
        return broker.high_watermark("orders", 0), broker.high_watermark("orders", 2)

    hw0, hw2 = run(scenario())
    assert hw0 == 1
    assert hw2 == 1


def test_produce_accepts_single_iterable_and_count():
    async def scenario() -> tuple[int, int, int]:
        broker = SimBroker(SimBrokerConfig())
        await broker.produce("t", 0, b"one")
        await broker.produce("t", 0, [b"two", b"three"])
        await broker.produce("t", 0, 4)
        zero = SimBroker(SimBrokerConfig())
        await zero.produce("t", 0, 0)
        return (
            broker.high_watermark("t", 0),
            zero.high_watermark("t", 0),
            broker.produced_total,
        )

    hw, zero_hw, produced = run(scenario())
    assert (hw, zero_hw, produced) == (7, 0, 7)


def test_payloads_are_lazy_rendered_at_fetch_time():
    async def scenario() -> tuple[int, bytes, bytes]:
        calls: list[tuple[str, int, int]] = []

        def factory(topic: str, partition: int, offset: int) -> bytes:
            calls.append((topic, partition, offset))
            return f"{topic}:{offset}".encode()

        broker = SimBroker(SimBrokerConfig(payload_bytes=16), payload_factory=factory)
        await broker.produce("t", 0, 5)
        factory_calls_after_produce = len(calls)
        first = await broker.get_one("t", 0, "g")
        second = await broker.get_one("t", 0, "g")
        assert isinstance(first, SimMessage) and isinstance(second, SimMessage)
        return factory_calls_after_produce, first.payload, second.payload

    after_produce, first_payload, second_payload = run(scenario())
    assert after_produce == 0
    assert first_payload == b"t:0"
    assert second_payload == b"t:1"


def test_default_payload_is_deterministic_offset_filler():
    async def scenario() -> tuple[bytes, bytes, bytes]:
        broker_a = SimBroker(SimBrokerConfig())
        broker_b = SimBroker(SimBrokerConfig())
        await broker_a.produce("t", 0, 2)
        await broker_b.produce("t", 0, 2)
        msg_a = await broker_a.get_one("t", 0, "g")
        msg_a2 = await broker_a.get_one("t", 0, "g")
        msg_b = await broker_b.get_one("t", 0, "g")
        assert isinstance(msg_a, SimMessage)
        assert isinstance(msg_a2, SimMessage)
        assert isinstance(msg_b, SimMessage)
        return msg_a.payload, msg_b.payload, msg_a2.payload

    a0, b0, a1 = run(scenario())
    assert len(a0) == 1024
    assert a0 == b0
    assert a0 != a1


def test_get_one_advances_cursor_and_lag_counts():
    async def scenario() -> tuple[int, int, int, int]:
        broker = SimBroker(SimBrokerConfig())
        await broker.produce("t", 0, 3)
        lag0 = broker.lag("t", 0, "g")
        first = await broker.get_one("t", 0, "g")
        second = await broker.get_one("t", 0, "g")
        assert isinstance(first, SimMessage) and isinstance(second, SimMessage)
        return (
            lag0,
            broker.consumed_total,
            broker.lag("t", 0, "g"),
            second.offset,
        )

    lag0, consumed, lag_after, offset = run(scenario())
    assert lag0 == 3
    assert (consumed, lag_after, offset) == (2, 1, 1)


def test_get_one_on_drained_partition_returns_timeout_value():
    async def scenario() -> SimMessage | Exception:
        broker = SimBroker(SimBrokerConfig())
        return await broker.get_one("t", 0, "g")

    result = run(scenario())
    assert isinstance(result, KafkaTimeoutError)


def test_get_many_drains_range_with_zero_loss():
    async def scenario() -> tuple[list[int], int, int]:
        broker = SimBroker(SimBrokerConfig())
        await broker.produce("t", 0, 100)
        batch = await broker.get_many("t", 0, "g", 1000)
        offsets = [m.offset for m in batch if isinstance(m, SimMessage)]
        rest = await broker.get_many("t", 0, "g", 1000)
        return offsets, broker.consumed_total, len(rest)

    offsets, consumed, rest_len = run(scenario())
    assert offsets == list(range(100))
    assert (consumed, rest_len) == (100, 0)


def test_produce_faults_returned_as_values_never_raised():
    async def scenario(seed: int) -> SimMessage | Exception | None:
        broker = SimBroker(
            SimBrokerConfig(
                seed=seed,
                faults=KafkaFaultConfig(
                    produce_buffer_timeout_pct=50.0, produce_closed_pct=50.0
                ),
            )
        )
        error = await broker.produce("t", 0, b"p")
        assert broker.produced_total == 0
        assert broker.high_watermark("t", 0) == 0
        return error

    timeout_seed = seed_with_bucket("k:p:t:0", (50.0, 50.0), 0)
    closed_seed = seed_with_bucket("k:p:t:0", (50.0, 50.0), 1)
    assert isinstance(run(scenario(timeout_seed)), KafkaTimeoutError)
    assert isinstance(run(scenario(closed_seed)), ProducerClosed)


def test_produce_without_faults_returns_none():
    async def scenario() -> Exception | None:
        broker = SimBroker(SimBrokerConfig())
        error = await broker.produce("t", 0, b"p")
        return error

    assert run(scenario()) is None


def test_fetch_faults_returned_as_values_and_keep_cursor():
    async def scenario(seed: int) -> SimMessage | Exception:
        broker = SimBroker(
            SimBrokerConfig(
                seed=seed,
                faults=KafkaFaultConfig(
                    fetch_timeout_pct=50.0, consumer_stopped_pct=50.0
                ),
            )
        )
        await broker.produce("t", 0, 2)
        batch = await broker.get_many("t", 0, "g", 10)
        assert len(batch) == 1 and isinstance(batch[0], Exception)
        assert broker.consumed_total == 0
        assert broker.lag("t", 0, "g") == 2
        return await broker.get_one("t", 0, "g")

    timeout_seed = seed_with_bucket("k:c:g:0", (50.0, 50.0), 0)
    stopped_seed = seed_with_bucket("k:c:g:0", (50.0, 50.0), 1)
    assert isinstance(run(scenario(timeout_seed)), KafkaTimeoutError)
    assert isinstance(run(scenario(stopped_seed)), ConsumerStoppedError)


def test_same_seed_replays_same_outcomes_and_payloads():
    async def scenario() -> tuple[list[str], list[bytes]]:
        broker = SimBroker(
            SimBrokerConfig(
                seed=11,
                faults=KafkaFaultConfig(
                    produce_buffer_timeout_pct=30.0,
                    fetch_timeout_pct=30.0,
                    consumer_stopped_pct=20.0,
                ),
            )
        )
        produce_kinds = []
        for _ in range(100):
            error = await broker.produce("t", 0, b"p")
            produce_kinds.append("ok" if error is None else type(error).__name__)
        payloads = []
        while True:
            batch = await broker.get_many("t", 0, "g", 10)
            if not batch:
                break
            payloads.extend(m.payload for m in batch if isinstance(m, SimMessage))
            if any(isinstance(m, Exception) for m in batch):
                break
        return produce_kinds, payloads

    first = run(scenario())
    second = run(scenario())
    assert first == second


def test_different_seed_changes_fault_outcomes():
    async def scenario(seed: int) -> list[str]:
        broker = SimBroker(
            SimBrokerConfig(
                seed=seed,
                faults=KafkaFaultConfig(produce_buffer_timeout_pct=50.0),
            )
        )
        kinds = []
        for _ in range(10):
            error = await broker.produce("t", 0, b"p")
            kinds.append("ok" if error is None else type(error).__name__)
        return kinds

    faulted = seed_with_bucket("k:p:t:0", (50.0,), 0)
    clean = seed_with_bucket("k:p:t:0", (50.0,), -1)
    assert asyncio.run(scenario(faulted)) != asyncio.run(scenario(clean))


def test_config_rejects_unknown_fields_and_bad_payload_bytes():
    try:
        SimBrokerConfig.model_validate({"nope": 1})
        raise AssertionError("expected ValidationError")
    except ValidationError:
        pass
    try:
        SimBrokerConfig(payload_bytes=0)
        raise AssertionError("expected ValidationError")
    except ValidationError:
        pass


def test_one_million_produce_and_consume_within_30s_budget():
    async def scenario() -> tuple[int, int, int, int]:
        broker = SimBroker(SimBrokerConfig())
        produce_error = await broker.produce("t", 0, 1_000_000)
        assert produce_error is None
        total = 0
        first_offset: int | None = None
        last_offset = -1
        while total < 1_000_000:
            batch = await broker.get_many("t", 0, "g", 10_000)
            assert batch, "get_many stalled before draining the log"
            for m in batch:
                assert isinstance(m, SimMessage)
                if first_offset is None:
                    first_offset = m.offset
                assert m.offset == last_offset + 1
                last_offset = m.offset
            total += len(batch)
        return (
            broker.produced_total,
            broker.consumed_total,
            broker.lag("t", 0, "g"),
            first_offset if first_offset is not None else -1,
        )

    start = time.perf_counter()
    produced, consumed, lag, first_offset = run(scenario())
    elapsed = time.perf_counter() - start
    assert first_offset == 0
    assert produced == consumed == 1_000_000
    assert lag == 0
    assert elapsed < 30.0
