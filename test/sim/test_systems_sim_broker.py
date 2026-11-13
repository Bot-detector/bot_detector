import asyncio
import time

import pytest
from aiokafka.errors import (
    ConsumerStoppedError,
    KafkaTimeoutError,
    ProducerClosed,
)
from pydantic import ValidationError

import dst as dst
from dst.faults import KafkaFaultConfig, bucket, draw
from dst.loop import running_clock
from dst.systems import KafkaConfig, SimBrokerError, SimFeedKafka
from dst.systems.sim_broker import SimBroker, SimBrokerConfig, SimMessage
from dst.systems.sim_costs import LinkError


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
    async def scenario(seed: int) -> tuple[type[Exception], int, int]:
        broker = SimBroker(
            SimBrokerConfig(
                seed=seed,
                faults=KafkaFaultConfig(
                    fetch_timeout_pct=50.0, consumer_stopped_pct=25.0
                ),
            )
        )
        await broker.produce("t", 0, 2)
        batch = await broker.get_many("t", 0, "g", 10)
        first = batch[0]
        assert isinstance(first, Exception)
        assert broker.consumed_total == 0
        assert broker.lag("t", 0, "g") == 2
        # a retry redraws (next attempt ordinal): the stream recovers
        # and drains both offsets, faults included as values; capped
        # because no attempt is guaranteed clean at 75% fault coverage
        values = [first]
        for _ in range(50):
            if broker.consumed_total == 2:
                break
            values.append(await broker.get_one("t", 0, "g"))
        assert broker.consumed_total == 2, "retry redraw never recovered"
        return type(first), len(values), broker.lag("t", 0, "g")

    timeout_seed = seed_with_bucket("k:c:t:g:0", (50.0, 25.0), 0)
    stopped_seed = seed_with_bucket("k:c:t:g:0", (50.0, 25.0), 1)
    for seed, wanted in (
        (timeout_seed, KafkaTimeoutError),
        (stopped_seed, ConsumerStoppedError),
    ):
        kind, attempts, lag = run(scenario(seed))
        assert kind is wanted
        assert attempts >= 3  # 2 messages + at least the seeded fault
        assert lag == 0


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


# --- SimFeedKafka: paced feed, fake-owned costs, fault values ----------


def run_scenario(coro):
    return dst.run(coro)


def feed_msg(result: SimMessage | Exception) -> SimMessage:
    assert isinstance(result, SimMessage)
    return result


def test_feed_rate_paces_consumption_in_virtual_time():
    async def scenario() -> tuple[float, int]:
        clock = running_clock()
        kafka = SimFeedKafka(
            KafkaConfig(feed_rate_s=100, parse_cost_s=0.0),
        )
        await kafka.start()
        for _ in range(10):
            await kafka.get_one()
        await kafka.stop()
        return clock.time(), kafka.produced_total

    result = run_scenario(scenario())
    elapsed, produced = result.value
    assert elapsed == pytest.approx(0.1, abs=0.05)  # 10 msgs at 100/s
    assert produced >= 10


def test_feed_offsets_are_monotonic():
    async def scenario() -> list[int]:
        kafka = SimFeedKafka(KafkaConfig(feed_rate_s=1000))
        await kafka.start()
        offsets = [feed_msg(await kafka.get_one()).offset for _ in range(20)]
        await kafka.stop()
        return offsets

    result = run_scenario(scenario())
    offsets = result.value
    assert offsets == sorted(offsets)
    assert len(set(offsets)) == len(offsets)


def test_feed_backlog_grows_when_consumer_is_slower_than_feed():
    async def scenario() -> tuple[int, int]:
        clock = running_clock()
        kafka = SimFeedKafka(
            KafkaConfig(feed_rate_s=1000, parse_cost_s=0.002),  # 500/s capacity
        )
        await kafka.start()
        deadline = clock.time() + 1.0
        while clock.time() < deadline:
            await kafka.get_one()
        await kafka.stop()
        return kafka.consumed_total, kafka.backlog

    result = run_scenario(scenario())
    consumed, backlog = result.value
    assert consumed < 1000  # feed outran the consumer
    assert backlog > 0  # broker retained the surplus


def test_feed_parks_when_consumer_is_faster_than_feed():
    async def scenario() -> int:
        clock = running_clock()
        kafka = SimFeedKafka(
            KafkaConfig(feed_rate_s=10, parse_cost_s=0.0),
        )
        await kafka.start()
        deadline = clock.time() + 1.0
        while clock.time() < deadline:
            await kafka.get_one()
        await kafka.stop()
        return kafka.consumed_total

    result = run_scenario(scenario())
    # the parked consumer tracks the feed rate exactly, not busy-spins
    assert result.value == pytest.approx(10, rel=0.2)


def test_feed_broker_errors_and_poison_come_back_as_values():
    async def scenario() -> tuple[list, int, int]:
        kafka = SimFeedKafka(
            KafkaConfig(
                feed_rate_s=1000,
                faults=KafkaFaultConfig(error_pct=10.0, poison_pct=10.0),
            ),
        )
        await kafka.start()
        out = [await kafka.get_one() for _ in range(100)]
        await kafka.stop()
        kinds = [m.kind for m in out if isinstance(m, SimBrokerError)]
        return out, kinds.count("broker_error"), kinds.count("poison")

    result = run_scenario(scenario())
    messages, errors, poisons = result.value
    assert "SimMessage" in [type(m).__name__ for m in messages]
    assert errors + poisons == len(
        [m for m in messages if isinstance(m, SimBrokerError)]
    )
    assert errors > 0 and poisons > 0


def test_feed_fault_stream_replays_with_same_seed():
    def scenario() -> list[str]:
        async def run_seed() -> list[str]:
            kafka = SimFeedKafka(
                KafkaConfig(
                    feed_rate_s=1000,
                    seed=42,
                    faults=KafkaFaultConfig(
                        error_pct=5.0, poison_pct=5.0, slow_fetch_pct=2.0
                    ),
                ),
            )
            await kafka.start()
            out = [await kafka.get_one() for _ in range(100)]
            await kafka.stop()
            return [
                m.kind if isinstance(m, SimBrokerError) else f"msg:{feed_msg(m).offset}"
                for m in out
            ]

        return run_scenario(run_seed()).value

    assert scenario() == scenario()


def test_feed_link_draws_replay_with_same_seed():
    def scenario() -> tuple[float, int]:
        async def run_seed() -> tuple[float, int]:
            kafka = SimFeedKafka(
                KafkaConfig(
                    feed_rate_s=1000,
                    seed=9,
                    fetch_mean_ms=2.0,
                    fetch_jitter_ms=1.0,
                ),
            )
            await kafka.start()
            for _ in range(20):
                await kafka.get_one()
            await kafka.stop()
            return kafka.link.latency_s, kafka.consumed_total

        return run_scenario(run_seed()).value

    assert scenario() == scenario()  # same seed, same draws


def test_feed_slow_fetch_triggers_app_side_timeout():
    async def scenario() -> str | None:
        kafka = SimFeedKafka(
            KafkaConfig(
                feed_rate_s=1000,
                faults=KafkaFaultConfig(slow_fetch_pct=100.0, slow_fetch_s=5.0),
            ),
        )
        await kafka.start()
        try:
            await asyncio.wait_for(kafka.get_one(), timeout=1.0)
            return "got message"
        except asyncio.TimeoutError:
            return "timeout"
        finally:
            await kafka.stop()

    first = run_scenario(scenario())
    second = run_scenario(scenario())
    assert first.value == second.value == "timeout"
    assert first.done and second.done
    assert first.virtual_time_s == pytest.approx(1.0)


def test_feed_parse_cost_caps_consumption_below_feed_rate():
    async def scenario() -> tuple[int, int]:
        clock = running_clock()
        kafka = SimFeedKafka(
            KafkaConfig(feed_rate_s=10_000, parse_cost_s=0.0002),  # 5k/s cpu cap
        )
        await kafka.start()
        deadline = clock.time() + 1.0
        while clock.time() < deadline:
            await kafka.get_one()
        await kafka.stop()
        return kafka.consumed_total, kafka.backlog

    result = run_scenario(scenario())
    consumed, backlog = result.value
    assert consumed <= 5_100  # cpu-bound, far below the 10k feed
    assert backlog > 0


def test_feed_message_costs_land_on_the_fake():
    async def scenario() -> tuple[int, int, float, float]:
        kafka = SimFeedKafka(
            KafkaConfig(feed_rate_s=1000, parse_cost_s=0.001),
        )
        await kafka.start()
        for _ in range(10):
            await kafka.get_one()
        await kafka.stop()
        return (
            kafka.cpu.calls,
            kafka.link.calls,
            kafka.cpu.busy_s,
            kafka.link.latency_s,
        )

    result = run_scenario(scenario())
    cpu_calls, link_calls, cpu_busy_s, link_latency_s = result.value
    assert cpu_calls == link_calls == 10  # one fetch + one parse per message
    assert cpu_busy_s == pytest.approx(0.01)  # 10 parses at 1ms
    assert link_latency_s > 0.0  # the link RTTs were paid


def test_feed_link_loss_surfaces_errors_as_values():
    async def scenario() -> list[str]:
        kafka = SimFeedKafka(
            KafkaConfig(feed_rate_s=1000, fetch_loss_pct=100.0),
        )
        await kafka.start()
        await kafka.get_one()  # 100% loss: every call returns LinkError
        out = [await kafka.get_one() for _ in range(3)]
        await kafka.stop()
        return [f"{type(m).__name__}: {m}" for m in out]

    result = run_scenario(scenario())
    assert result.done
    assert result.value == ["LinkError: link lost (seeded)"] * 3  # values, not raises


def test_feed_get_one_after_stop_drains_as_timeout_value():
    async def scenario() -> Exception:
        kafka = SimFeedKafka(KafkaConfig(feed_rate_s=1000))
        await kafka.start()
        await kafka.stop()  # nothing produced, nothing in flight
        # must return the drained error instead of parking forever: a
        # parked loop keeps the virtual loop non-idle and defeats
        # DSTIdleError (the regression this test pins)
        return await kafka.get_one()

    result = run_scenario(scenario())
    assert result.done
    assert isinstance(result.value, KafkaTimeoutError)
    assert "drained" in str(result.value)


def test_eager_log_rejects_a_second_consumer_group():
    async def scenario() -> None:
        broker = SimBroker(
            SimBrokerConfig(seed=0),
            payload_factory=lambda topic, partition, offset: b"eager",
        )
        await broker.produce("t", 0, [b"alpha", b"beta"])
        first = await broker.get_one("t", 0, "g1")
        assert isinstance(first, SimMessage)
        assert first.payload == b"alpha"
        # the eager log is claimed by g1; a second group must fail loud,
        # not read offset-derived filler for arrival-time bytes
        try:
            await broker.get_one("t", 0, "g2")
        except AssertionError:
            return
        raise AssertionError("second eager group did not assert")

    result = run_scenario(scenario())
    assert result.done
    assert result.error is None


def test_feed_zero_loss_never_fails():
    async def scenario() -> int:
        clock = running_clock()
        kafka = SimFeedKafka(KafkaConfig(feed_rate_s=10_000, fetch_loss_pct=0.0))
        await kafka.start()
        failures = 0
        deadline = clock.time() + 0.5
        while clock.time() < deadline:
            if isinstance(await kafka.get_one(), Exception):
                failures += 1
        await kafka.stop()
        return failures

    result = run_scenario(scenario())
    assert result.value == 0  # 0 pct is the negative space: no faults


def test_fetch_fault_knobs_resolve_boundary_buckets():
    async def consumed_ok() -> int:
        kafka = SimFeedKafka(
            KafkaConfig(
                feed_rate_s=10_000,
                faults=KafkaFaultConfig(fetch_timeout_pct=0.0),
            ),
        )
        await kafka.start()
        delivered = 0
        for _ in range(50):
            if isinstance(await kafka.get_one(), SimMessage):
                delivered += 1
        await kafka.stop()
        return delivered

    async def faulted_kinds() -> list[str]:
        kafka = SimFeedKafka(
            KafkaConfig(
                feed_rate_s=10_000,
                faults=KafkaFaultConfig(fetch_timeout_pct=100.0),
            ),
        )
        await kafka.start()
        kinds = [type(r).__name__ for r in [await kafka.get_one() for _ in range(5)]]
        await kafka.stop()
        return kinds

    assert run_scenario(consumed_ok()).value == 50  # 0 pct: every fetch delivers
    assert run_scenario(faulted_kinds()).value == ["KafkaTimeoutError"] * 5


def test_feed_error_plus_poison_over_100_pct_rejected():
    with pytest.raises(ValidationError, match="<= 100"):
        KafkaConfig(faults=KafkaFaultConfig(error_pct=60.0, poison_pct=60.0))


def test_feed_config_rejects_bad_link_knobs():
    with pytest.raises(ValidationError):
        KafkaConfig(fetch_mean_ms=-1.0)
    with pytest.raises(ValidationError):
        KafkaConfig(fetch_jitter_ms=-1.0)
    with pytest.raises(ValidationError):
        KafkaConfig(bandwidth_mbps=0.0)
    with pytest.raises(ValidationError):
        KafkaConfig(fetch_loss_pct=101.0)
    with pytest.raises(ValidationError):
        KafkaConfig(fetch_loss_pct=-0.5)


def test_feed_stopped_producer_leaves_no_pending_tasks():
    async def scenario() -> None:
        kafka = SimFeedKafka(KafkaConfig(feed_rate_s=1000))
        await kafka.start()
        for _ in range(5):
            await kafka.get_one()
        await kafka.stop()

    result = run_scenario(scenario())
    assert result.done
    assert result.pending_tasks == []


def test_feed_unstopped_producer_is_reported():
    async def scenario() -> None:
        kafka = SimFeedKafka(KafkaConfig(feed_rate_s=1000))
        await kafka.start()
        await kafka.get_one()
        # no stop(): the producer leaks

    result = run_scenario(scenario())
    assert result.done
    assert len(result.pending_tasks) == 1
    assert "sim-kafka-producer" in result.pending_tasks[0]


def test_feed_broker_outage_fails_without_losing_arrivals():
    async def scenario() -> tuple[list[str], list[int]]:
        kafka = SimFeedKafka(KafkaConfig(feed_rate_s=1000))
        await kafka.start()
        await kafka.get_one()  # consume the first arrival
        kafka.set_down(True)
        during = [await kafka.get_one() for _ in range(3)]
        await asyncio.sleep(0.5)  # arrivals keep queueing during the outage
        kafka.set_down(False)
        after = [feed_msg(await kafka.get_one()).offset for _ in range(3)]
        await kafka.stop()
        kinds = [m.kind for m in during if isinstance(m, SimBrokerError)]
        return kinds, after

    result = run_scenario(scenario())
    assert result.done
    kinds, offsets_after = result.value
    assert kinds == ["broker_down"] * 3  # outage errors, as values
    assert offsets_after == sorted(offsets_after)  # stream resumes in order


def test_feed_pace_carries_fractional_rates():
    async def scenario() -> int:
        clock = running_clock()
        kafka = SimFeedKafka(KafkaConfig(feed_rate_s=10))
        await kafka.start()
        deadline = clock.time() + 1.0
        while clock.time() < deadline:
            await kafka.get_one()
        await kafka.stop()
        return kafka.produced_total

    result = run_scenario(scenario())
    # 10/s over 1s: fractional carry, not one message per tick
    assert result.value == pytest.approx(10, rel=0.2)


def test_feed_start_delay_holds_the_stream():
    async def scenario() -> tuple[int, float]:
        clock = running_clock()
        kafka = SimFeedKafka(
            KafkaConfig(feed_rate_s=1000, start_delay_s=1.0),
        )
        await kafka.start()
        first = await kafka.get_one()  # parks until the delay elapses
        return feed_msg(first).offset, clock.time()

    result = run_scenario(scenario())
    offset, when = result.value
    assert offset == 0
    assert when == pytest.approx(1.0, abs=0.05)


def test_link_error_is_a_value_not_a_raise():
    assert issubclass(LinkError, Exception)  # errors-as-values contract
    assert issubclass(SimBrokerError, Exception)
