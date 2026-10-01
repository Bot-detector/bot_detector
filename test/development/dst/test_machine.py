"""VirtualMachine: cpu serialization, io profiles, seeded faults."""

import asyncio

import pytest
from pydantic import ValidationError

import dst as dst
from dst import (
    FaultSchedule,
    IoConfig,
    IoError,
    MachineConfig,
    VirtualClock,
    VirtualMachine,
)


def make_machine(**kwargs) -> VirtualMachine:
    return VirtualMachine(MachineConfig(**kwargs), clock=VirtualClock())


def test_sequential_cpu_callers_never_wait():
    async def scenario() -> tuple[float, float]:
        machine = VirtualMachine(MachineConfig())
        first = await machine.cpu(0.5, what="a")
        second = await machine.cpu(0.5, what="b")
        return first.waited_s, second.waited_s

    result = dst.run(scenario())
    assert result.done
    assert result.value == (0.0, 0.0)


def test_concurrent_cpu_calls_queue_fifo():
    async def scenario() -> list[tuple[str, float, float]]:
        machine = VirtualMachine(MachineConfig())

        async def worker(name: str, cost: float) -> tuple[str, float, float]:
            grant = await machine.cpu(cost, what=name)
            return (grant.what, grant.waited_s, grant.finished_s)

        return list(
            await asyncio.gather(
                worker("a", 1.0),
                worker("b", 1.0),
            )
        )

    result = dst.run(scenario())
    assert result.done
    assert result.value == [
        ("a", 0.0, 1.0),
        ("b", 1.0, 2.0),
    ]


def test_saturated_pump_sustains_capacity_rate():
    async def scenario() -> tuple[int, float]:
        machine = VirtualMachine(MachineConfig())
        processed = 0
        while machine.clock.time() < 10.0:
            await machine.cpu(0.001, what="msg")
            processed += 1
        return processed, machine.utilization()

    result = dst.run(scenario())
    assert result.done
    processed, utilization = result.value
    assert processed == pytest.approx(10_000, rel=1e-3)
    assert utilization == pytest.approx(1.0)


def test_cpu_rejects_bad_costs():
    machine = make_machine()

    async def bad(value: float) -> None:
        await machine.cpu(value)

    with pytest.raises(ValueError, match="finite"):
        asyncio.run(bad(float("nan")))
    with pytest.raises(ValueError, match=">= 0"):
        asyncio.run(bad(-1.0))


def test_io_draws_are_deterministic_per_seed():
    async def scenario() -> list[float]:
        config = MachineConfig(io={"disk": IoConfig(mean_ms=5, jitter_ms=2)}, seed=42)
        machine = VirtualMachine(config)
        return [(await machine.io("disk")).latency_s for _ in range(10)]

    first = dst.run(scenario())
    second = dst.run(scenario())
    assert first.done and second.done
    assert first.value == second.value


def test_io_jitter_stays_within_bounds():
    async def scenario() -> list[float]:
        config = MachineConfig(io={"net": IoConfig(mean_ms=10, jitter_ms=4)})
        machine = VirtualMachine(config)
        return [(await machine.io("net")).latency_s for _ in range(200)]

    result = dst.run(scenario())
    assert all(6.0 / 1000 <= d <= 14.0 / 1000 for d in result.value)


def test_io_unknown_system_is_config_error():
    async def scenario() -> None:
        await make_machine().io("nope")

    result = dst.run(scenario())
    assert isinstance(result.error, ValueError)
    assert "nope" in str(result.error)


def test_io_failures_come_back_as_values():
    async def scenario() -> list[Exception | None]:
        config = MachineConfig(io={"net": IoConfig(mean_ms=1, fail_pct=100.0)})
        machine = VirtualMachine(config)
        return [(await machine.io("net")).error for _ in range(5)]

    result = dst.run(scenario())
    assert result.done
    assert len(result.value) == 5
    assert all(isinstance(e, IoError) for e in result.value)


def test_io_zero_fail_pct_never_fails():
    async def scenario() -> int:
        config = MachineConfig(io={"net": IoConfig(mean_ms=1)})
        machine = VirtualMachine(config)
        failures = 0
        for _ in range(50):
            if (await machine.io("net")).error is not None:
                failures += 1
        return failures

    result = dst.run(scenario())
    assert result.value == 0


def test_io_throughput_adds_transfer_time():
    async def scenario() -> float:
        config = MachineConfig(
            io={"net": IoConfig(mean_ms=1, throughput_mbps=8.0)}  # 1 MB/s
        )
        machine = VirtualMachine(config)
        return (await machine.io("net", n_bytes=1_000_000)).latency_s

    result = dst.run(scenario())
    assert result.value == pytest.approx(1.0, rel=1e-3)  # 8 Mbit at 8 Mbps


def test_stalls_hit_cpu_calls():
    async def scenario() -> tuple[float, float, float]:
        config = MachineConfig(faults=FaultSchedule(stall_pct=100.0, stall_s=2.0))
        machine = VirtualMachine(config)
        grant = await machine.cpu(0.001)
        return grant.stalled_s, grant.finished_s, machine.stall_s

    result = dst.run(scenario())
    assert result.done
    stalled_s, finished_s, total_stall_s = result.value
    assert stalled_s == 2.0
    assert finished_s == pytest.approx(2.001)
    assert total_stall_s == 2.0


def test_stall_eats_machine_capacity():
    async def scenario() -> tuple[int, int]:
        config = MachineConfig(faults=FaultSchedule(stall_pct=10.0, stall_s=0.1))
        machine = VirtualMachine(config)
        processed = 0
        while machine.clock.time() < 10.0:
            await machine.cpu(0.001)
            processed += 1
        return processed, machine.stalls

    result = dst.run(scenario())
    processed, stalls = result.value
    assert 100 < processed < 5_000  # well below the 10k no-fault capacity
    assert stalls > 0


def test_machine_binds_to_running_dst_loop_clock():
    async def scenario() -> float:
        machine = VirtualMachine(MachineConfig())
        await machine.cpu(0.5)
        return machine.clock.time()

    result = dst.run(scenario(), start_s=100)
    assert result.value == pytest.approx(100.5)


def test_machine_outside_dst_loop_needs_a_clock():
    async def construct() -> None:
        await VirtualMachine(MachineConfig()).cpu(0.1)

    with pytest.raises(RuntimeError, match="clock"):
        asyncio.run(construct())


def test_full_run_replays_with_same_seed():
    async def scenario() -> tuple[float, float, float]:
        config = MachineConfig(
            seed=7,
            io={"net": IoConfig(mean_ms=3, jitter_ms=3)},
            faults=FaultSchedule(stall_pct=20.0, stall_s=0.05),
        )
        machine = VirtualMachine(config)
        for _ in range(20):
            await machine.io("net")
            await machine.cpu(0.002)
        return machine.clock.time(), machine.stalls, machine.io_failures

    first = dst.run(scenario())
    second = dst.run(scenario())
    assert first.done and second.done
    assert first.value == second.value


def test_invalid_config_rejected():
    with pytest.raises(ValidationError):
        MachineConfig(io={"net": IoConfig(mean_ms=0)})
    with pytest.raises(ValidationError):
        MachineConfig(io={"net": IoConfig(mean_ms=1, fail_pct=101)})
    with pytest.raises(ValidationError):
        MachineConfig(faults=FaultSchedule(stall_pct=-1))
