"""FakeKafka: paced feed, machine costs, seeded protocol faults."""

import asyncio

import pytest

import dst as dst
from dst import (
    IoConfig,
    MachineConfig,
    SimResult,
    VirtualClock,
    VirtualMachine,
)
from dst.systems import (
    FakeKafka,
    FakeKafkaError,
    KafkaConfig,
    KafkaFaults,
    KafkaMessage,
)

KAFKA_IO = {"kafka": IoConfig(mean_ms=1)}


def make_machine(clock: VirtualClock | None = None, **io_kwargs) -> VirtualMachine:
    return VirtualMachine(
        MachineConfig(io={"kafka": IoConfig(mean_ms=1, **io_kwargs)}), clock=clock
    )


def consume_kafka(kafka: FakeKafka, n: int) -> SimResult:
    async def scenario() -> list:
        await kafka.start()
        out = [await kafka.get_one() for _ in range(n)]
        await kafka.stop()
        return out

    return dst.run(scenario())


def msg(result: KafkaMessage | Exception) -> "KafkaMessage":
    assert isinstance(result, KafkaMessage)
    return result


def test_feed_rate_paces_consumption_in_virtual_time():
    async def scenario() -> tuple[float, int]:
        machine = VirtualMachine(MachineConfig(io={"kafka": IoConfig(mean_ms=0.01)}))
        kafka = FakeKafka(machine, KafkaConfig(rate_s=100, parse_cost_s=0.0))
        await kafka.start()
        for _ in range(10):
            await kafka.get_one()
        await kafka.stop()
        return machine.clock.time(), kafka.produced_total

    result = dst.run(scenario())
    elapsed, produced = result.value
    assert elapsed == pytest.approx(0.1, abs=0.05)  # 10 msgs at 100/s
    assert produced >= 10


def test_offsets_are_monotonic():
    async def scenario() -> list[int]:
        kafka = FakeKafka(make_machine(), KafkaConfig(rate_s=1000))
        await kafka.start()
        offsets = [msg(await kafka.get_one()).offset for _ in range(20)]
        await kafka.stop()
        return offsets

    result = dst.run(scenario())
    offsets = result.value
    assert offsets == sorted(offsets)
    assert len(set(offsets)) == len(offsets)


def test_backlog_grows_when_consumer_is_slower_than_feed():
    async def scenario() -> tuple[int, int]:
        machine = VirtualMachine(MachineConfig(io={"kafka": IoConfig(mean_ms=0.01)}))
        kafka = FakeKafka(
            machine,
            KafkaConfig(rate_s=1000, parse_cost_s=0.002),  # 500/s capacity
        )
        await kafka.start()
        deadline = machine.clock.time() + 1.0
        while machine.clock.time() < deadline:
            await kafka.get_one()
        await kafka.stop()
        return kafka.consumed_total, kafka.backlog

    result = dst.run(scenario())
    consumed, backlog = result.value
    assert consumed < 1000  # feed outran the consumer
    assert backlog > 0  # broker retained the surplus


def test_broker_errors_and_poison_come_back_as_values():
    async def scenario() -> tuple[list, int, int]:
        kafka = FakeKafka(
            make_machine(),
            KafkaConfig(
                rate_s=1000,
                faults=KafkaFaults(error_pct=10.0, poison_pct=10.0),
            ),
        )
        await kafka.start()
        out = [await kafka.get_one() for _ in range(100)]
        await kafka.stop()
        return out, kafka.errors_returned, kafka.poisons_returned

    result = dst.run(scenario())
    messages, errors, poisons = result.value
    kinds = [m.kind for m in messages if isinstance(m, FakeKafkaError)]
    assert "KafkaMessage" in [type(m).__name__ for m in messages]
    assert set(kinds) <= {"broker_error", "poison"}
    assert errors + poisons == len(kinds)
    assert errors > 0 and poisons > 0


def test_fault_stream_replays_with_same_seed():
    def scenario() -> list[str]:
        async def run() -> list[str]:
            kafka = FakeKafka(
                make_machine(),
                KafkaConfig(
                    rate_s=1000,
                    seed=42,
                    faults=KafkaFaults(error_pct=5.0, poison_pct=5.0, slow_pct=2.0),
                ),
            )
            await kafka.start()
            out = [await kafka.get_one() for _ in range(100)]
            await kafka.stop()
            return [
                m.kind if isinstance(m, FakeKafkaError) else f"msg:{msg(m).offset}"
                for m in out
            ]

        return dst.run(run()).value

    assert scenario() == scenario()


def test_slow_fetch_triggers_app_side_timeout():
    async def scenario() -> str | None:
        machine = VirtualMachine(MachineConfig(io={"kafka": IoConfig(mean_ms=0.01)}))
        kafka = FakeKafka(
            machine,
            KafkaConfig(rate_s=1000, faults=KafkaFaults(slow_pct=100.0, slow_s=5.0)),
        )
        await kafka.start()
        try:
            await asyncio.wait_for(kafka.get_one(), timeout=1.0)
            return "got message"
        except asyncio.TimeoutError:
            return "timeout"
        finally:
            await kafka.stop()

    first = dst.run(scenario())
    second = dst.run(scenario())
    assert first.value == second.value == "timeout"
    assert first.done and second.done
    assert first.virtual_time_s == pytest.approx(1.0)


def test_parse_cost_caps_consumption_below_feed_rate():
    async def scenario() -> tuple[int, int]:
        machine = VirtualMachine(MachineConfig(io={"kafka": IoConfig(mean_ms=0.01)}))
        kafka = FakeKafka(
            machine,
            KafkaConfig(rate_s=10_000, parse_cost_s=0.0002),  # 5k/s cpu cap
        )
        await kafka.start()
        deadline = machine.clock.time() + 1.0
        while machine.clock.time() < deadline:
            await kafka.get_one()
        await kafka.stop()
        return kafka.consumed_total, kafka.backlog

    result = dst.run(scenario())
    consumed, backlog = result.value
    assert consumed <= 5_100  # cpu-bound, far below the 10k feed
    assert backlog > 0


def test_message_costs_land_on_the_machine():
    async def scenario() -> tuple[int, float]:
        machine = VirtualMachine(MachineConfig(io={"kafka": IoConfig(mean_ms=0.01)}))
        kafka = FakeKafka(machine, KafkaConfig(rate_s=1000, parse_cost_s=0.001))
        await kafka.start()
        for _ in range(10):
            await kafka.get_one()
        await kafka.stop()
        return machine.cpu_calls, machine.io_latency_s

    result = dst.run(scenario())
    cpu_calls, io_latency = result.value
    assert cpu_calls == 10
    assert io_latency >= 10 * 0.00001  # 10 fetches at mean 0.01ms


def test_unknown_io_system_fails_at_construction():
    machine = VirtualMachine(MachineConfig(), clock=VirtualClock())
    with pytest.raises(ValueError, match="kafka"):
        FakeKafka(machine, KafkaConfig())


def test_error_plus_poison_over_100_pct_rejected():
    machine = make_machine(clock=VirtualClock())
    with pytest.raises(ValueError, match="<= 100"):
        FakeKafka(
            machine,
            KafkaConfig(faults=KafkaFaults(error_pct=60.0, poison_pct=60.0)),
        )


def test_stopped_producer_leaves_no_pending_tasks():
    async def scenario() -> None:
        kafka = FakeKafka(make_machine(), KafkaConfig(rate_s=1000))
        await kafka.start()
        for _ in range(5):
            await kafka.get_one()
        await kafka.stop()

    result = dst.run(scenario())
    assert result.done
    assert result.pending_tasks == []


def test_unstopped_producer_is_reported():
    async def scenario() -> None:
        kafka = FakeKafka(make_machine(), KafkaConfig(rate_s=1000))
        await kafka.start()
        await kafka.get_one()
        # no stop(): the producer leaks

    result = dst.run(scenario())
    assert result.done
    assert len(result.pending_tasks) == 1
    assert "sim-kafka-producer" in result.pending_tasks[0]


def test_broker_outage_fails_without_losing_arrivals():
    async def scenario() -> tuple[list[str], list[int]]:
        machine = VirtualMachine(MachineConfig(io={"kafka": IoConfig(mean_ms=0.01)}))
        kafka = FakeKafka(machine, KafkaConfig(rate_s=1000))
        await kafka.start()
        await kafka.get_one()  # consume the first arrival
        kafka.set_down(True)
        during = [await kafka.get_one() for _ in range(3)]
        await asyncio.sleep(0.5)  # arrivals keep queueing during the outage
        kafka.set_down(False)
        after = [msg(await kafka.get_one()).offset for _ in range(3)]
        await kafka.stop()
        kinds = [m.kind for m in during if isinstance(m, FakeKafkaError)]
        return kinds, after

    result = dst.run(scenario())
    assert result.done
    kinds, offsets_after = result.value
    assert kinds == ["broker_down"] * 3  # outage errors, as values
    assert offsets_after == sorted(offsets_after)  # stream resumes in order
