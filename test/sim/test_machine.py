"""Machine: subsystems for cpu, memory, network, disk, processes."""

import asyncio

import pytest
from pydantic import ValidationError

import dst as dst
from dst import (
    CpuConfig,
    DiskConfig,
    Machine,
    MachineConfig,
    MemoryConfig,
    NetworkConfig,
    ProcessConfig,
    VirtualClock,
)
from dst.machine import Memory
from dst.units import MB


def make_machine(**kwargs) -> Machine:
    return Machine(MachineConfig(**kwargs), clock=VirtualClock())


# --- cpu ---------------------------------------------------------------


def test_sequential_cpu_callers_never_wait():
    async def scenario() -> tuple[float, float]:
        machine = Machine()
        first = await machine.cpu.work(0.5, what="a")
        second = await machine.cpu.work(0.5, what="b")
        return first.waited_s, second.waited_s

    result = dst.run(scenario())
    assert result.done
    assert result.value == (0.0, 0.0)


def test_concurrent_cpu_calls_queue_fifo():
    async def scenario() -> list[tuple[str, float, float]]:
        machine = Machine()

        async def worker(name: str, cost: float) -> tuple[str, float, float]:
            grant = await machine.cpu.work(cost, what=name)
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
        machine = Machine()
        processed = 0
        while machine.clock.time() < 10.0:
            await machine.cpu.work(0.001, what="msg")
            processed += 1
        return processed, machine.cpu.utilization()

    result = dst.run(scenario())
    assert result.done
    processed, utilization = result.value
    assert processed == pytest.approx(10_000, rel=1e-3)
    assert utilization == pytest.approx(1.0)


def test_cores_scale_capacity():
    async def scenario() -> tuple[int, int]:
        one = Machine(MachineConfig(cpu=CpuConfig(cores=1)))
        four = Machine(MachineConfig(cpu=CpuConfig(cores=4)))
        processed_one = 0
        while one.clock.time() < 1.0:
            await one.cpu.work(0.001)
            processed_one += 1
        processed_four = 0
        start_s = four.clock.time()
        while four.clock.time() < start_s + 1.0:
            await four.cpu.work(0.001)
            processed_four += 1
        return processed_one, processed_four

    result = dst.run(scenario())
    assert result.done
    one, four = result.value
    assert one == pytest.approx(1_000, rel=1e-3)
    assert four == pytest.approx(4_000, rel=1e-3)


def test_set_load_slows_work_deterministically():
    async def scenario() -> float:
        machine = Machine()
        machine.cpu.set_load(0.9)  # capacity drops to 0.1 cpu-s/s
        grant = await machine.cpu.work(0.05)
        return grant.finished_s

    result = dst.run(scenario())
    assert result.done
    assert result.value == pytest.approx(0.5)  # 0.05 / 0.1


def test_background_load_shows_in_utilization_when_idle():
    async def scenario() -> float:
        machine = Machine()
        machine.cpu.set_load(0.5)
        machine.clock.advance(10.0)
        return machine.cpu.utilization()

    result = dst.run(scenario())
    assert result.done
    assert result.value == pytest.approx(0.5)


def test_cpu_rejects_bad_costs_and_loads():
    machine = make_machine()

    async def bad_work(value: float) -> None:
        await machine.cpu.work(value)

    with pytest.raises(ValueError, match="finite"):
        asyncio.run(bad_work(float("nan")))
    with pytest.raises(ValueError, match=">= 0"):
        asyncio.run(bad_work(-1.0))
    with pytest.raises(ValueError, match=r"\[0, 1\)"):
        machine.cpu.set_load(1.0)
    with pytest.raises(ValueError, match=r"\[0, 1\)"):
        machine.cpu.set_load(-0.1)


def test_queued_s_reports_pending_work():
    async def scenario() -> float:
        machine = Machine()
        await machine.cpu.work(1.0)
        task = asyncio.create_task(machine.cpu.work(1.0))
        await asyncio.sleep(0.0)  # let the task admit
        queued = machine.cpu.queued_s()
        await task
        return queued

    result = dst.run(scenario())
    assert result.done
    assert result.value == pytest.approx(1.0)


# --- memory ------------------------------------------------------------


def test_memory_consume_release_pressure():
    memory = Memory(MemoryConfig(total_bytes=4 * MB))
    memory.consume(MB)
    assert memory.used_bytes == MB
    assert memory.pressure == pytest.approx(0.25)
    memory.consume(3 * MB)
    assert memory.pressure == pytest.approx(1.0)
    assert memory.peak_bytes == 4 * MB
    memory.release(2 * MB)
    assert memory.used_bytes == 2 * MB
    assert memory.pressure == pytest.approx(0.5)
    assert memory.consumes == 2 and memory.releases == 1


def test_memory_overcommit_and_overrelease_rejected():
    memory = Memory(MemoryConfig(total_bytes=MB))
    with pytest.raises(ValueError, match="out of memory"):
        memory.consume(MB + 1)
    with pytest.raises(ValueError, match=">= 0"):
        memory.consume(-1)
    memory.consume(MB)
    with pytest.raises(ValueError, match="cannot release"):
        memory.release(MB + 1)


# --- network -----------------------------------------------------------


def test_network_draws_are_deterministic_per_seed():
    async def scenario() -> list[float]:
        config = MachineConfig(network=NetworkConfig(mean_ms=5, jitter_ms=2), seed=42)
        machine = Machine(config)
        return [(await machine.network.fetch()).latency_s for _ in range(10)]

    first = dst.run(scenario())
    second = dst.run(scenario())
    assert first.done and second.done
    assert first.value == second.value


def test_network_jitter_stays_within_bounds():
    async def scenario() -> list[float]:
        machine = Machine(MachineConfig(network=NetworkConfig(mean_ms=10, jitter_ms=4)))
        return [(await machine.network.fetch()).latency_s for _ in range(200)]

    result = dst.run(scenario())
    assert all(6.0 / 1000 <= d <= 14.0 / 1000 for d in result.value)


def test_packet_loss_comes_back_as_values():
    async def scenario() -> list[Exception | None]:
        config = MachineConfig(network=NetworkConfig(mean_ms=1, packet_loss_pct=100.0))
        machine = Machine(config)
        return [(await machine.network.fetch()).error for _ in range(5)]

    result = dst.run(scenario())
    assert result.done
    assert len(result.value) == 5
    assert all(isinstance(e, dst.IoError) and "packet" in str(e) for e in result.value)


def test_zero_packet_loss_never_fails():
    async def scenario() -> int:
        machine = Machine(MachineConfig(network=NetworkConfig(mean_ms=1)))
        failures = 0
        for _ in range(50):
            if (await machine.network.fetch()).error is not None:
                failures += 1
        return failures

    result = dst.run(scenario())
    assert result.value == 0


def test_bandwidth_adds_transfer_time():
    async def scenario() -> float:
        config = MachineConfig(
            network=NetworkConfig(mean_ms=1, bandwidth_mbps=8.0)  # 1 MB/s
        )
        machine = Machine(config)
        return (await machine.network.fetch(n_bytes=1_000_000)).latency_s

    result = dst.run(scenario())
    assert result.value == pytest.approx(1.0, rel=1e-3)  # 8 Mbit at 8 Mbps


def test_partition_fails_fast_and_heal_restores():
    async def scenario() -> tuple[list[str], int, float]:
        machine = Machine(MachineConfig(network=NetworkConfig(mean_ms=1)))
        draws_before = machine.random.draws
        machine.network.partition()
        during = [(await machine.network.fetch()).error for _ in range(3)]
        draws_partitioned = machine.random.draws  # partition consumed none
        machine.network.heal()
        ok = await machine.network.fetch()
        return (
            [str(e) for e in during],
            draws_partitioned - draws_before,
            ok.latency_s,
        )

    result = dst.run(scenario())
    assert result.done
    errors, draws_used, latency = result.value
    assert errors == ["network partitioned"] * 3
    assert draws_used == 0
    assert latency > 0.0


# --- disk --------------------------------------------------------------


def test_disk_draws_are_deterministic_per_seed():
    async def scenario() -> list[float]:
        config = MachineConfig(disk=DiskConfig(mean_ms=5, jitter_ms=2), seed=42)
        machine = Machine(config)
        return [(await machine.disk.read()).latency_s for _ in range(10)]

    first = dst.run(scenario())
    second = dst.run(scenario())
    assert first.done and second.done
    assert first.value == second.value


def test_disk_failures_come_back_as_values():
    async def scenario() -> list[Exception | None]:
        config = MachineConfig(disk=DiskConfig(mean_ms=1, fail_pct=100.0))
        machine = Machine(config)
        return [(await machine.disk.write(n_bytes=10)).error for _ in range(5)]

    result = dst.run(scenario())
    assert result.done
    assert all(isinstance(e, dst.IoError) and "write" in str(e) for e in result.value)


def test_disk_latency_counts_toward_machine_totals():
    async def scenario() -> tuple[int, float]:
        machine = Machine(MachineConfig(disk=DiskConfig(mean_ms=1)))
        await machine.disk.read()
        await machine.disk.write()
        return machine.disk.calls, machine.disk.latency_s

    result = dst.run(scenario())
    calls, latency_s = result.value
    assert calls == 2
    assert latency_s >= 2 * 0.001


# --- processes ---------------------------------------------------------


def test_stalls_hit_cpu_work():
    async def scenario() -> tuple[float, float, float]:
        config = MachineConfig(processes=ProcessConfig(stall_pct=100.0, stall_s=2.0))
        machine = Machine(config)
        grant = await machine.cpu.work(0.001)
        return grant.stalled_s, grant.finished_s, machine.processes.stall_s

    result = dst.run(scenario())
    assert result.done
    stalled_s, finished_s, total_stall_s = result.value
    assert stalled_s == 2.0
    assert finished_s == pytest.approx(2.001)
    assert total_stall_s == 2.0


def test_stall_eats_machine_capacity():
    async def scenario() -> tuple[int, int]:
        config = MachineConfig(processes=ProcessConfig(stall_pct=10.0, stall_s=0.1))
        machine = Machine(config)
        processed = 0
        while machine.clock.time() < 10.0:
            await machine.cpu.work(0.001)
            processed += 1
        return processed, machine.processes.stalls

    result = dst.run(scenario())
    processed, stalls = result.value
    assert 100 < processed < 5_000  # well below the 10k no-fault capacity
    assert stalls > 0


def test_process_pause_waits_out_the_stall():
    async def scenario() -> float:
        config = MachineConfig(processes=ProcessConfig(stall_pct=100.0, stall_s=3.0))
        machine = Machine(config)
        await machine.processes.pause()
        return machine.clock.time()

    result = dst.run(scenario())
    assert result.value == pytest.approx(3.0)


# --- machine assembly --------------------------------------------------


def test_machine_clock_advances():
    machine = make_machine()
    assert machine.clock.advance(10.0) == pytest.approx(10.0)
    assert machine.clock.time() == pytest.approx(10.0)


def test_machine_binds_to_running_dst_loop_clock():
    async def scenario() -> float:
        machine = Machine()
        await machine.cpu.work(0.5)
        return machine.clock.time()

    result = dst.run(scenario(), start_s=100)
    assert result.value == pytest.approx(100.5)


def test_machine_outside_dst_loop_needs_a_clock():
    async def construct() -> None:
        await Machine().cpu.work(0.1)

    with pytest.raises(RuntimeError, match="clock"):
        asyncio.run(construct())


def test_full_run_replays_with_same_seed():
    async def scenario() -> tuple[float, int, int]:
        config = MachineConfig(
            seed=7,
            network=NetworkConfig(mean_ms=3, jitter_ms=3),
            disk=DiskConfig(mean_ms=2, jitter_ms=2),
            processes=ProcessConfig(stall_pct=20.0, stall_s=0.05),
        )
        machine = Machine(config)
        for _ in range(20):
            await machine.network.fetch()
            await machine.cpu.work(0.002)
            await machine.disk.read()
        return machine.clock.time(), machine.processes.stalls, machine.disk.failures

    first = dst.run(scenario())
    second = dst.run(scenario())
    assert first.done and second.done
    assert first.value == second.value


def test_invalid_config_rejected():
    with pytest.raises(ValidationError):
        MachineConfig(network=NetworkConfig(mean_ms=0))
    with pytest.raises(ValidationError):
        MachineConfig(network=NetworkConfig(mean_ms=1, packet_loss_pct=101))
    with pytest.raises(ValidationError):
        MachineConfig(disk=DiskConfig(mean_ms=1, fail_pct=101))
    with pytest.raises(ValidationError):
        MachineConfig(processes=ProcessConfig(stall_pct=-1))
    with pytest.raises(ValidationError):
        MachineConfig(cpu=CpuConfig(cores=0))
    with pytest.raises(ValidationError):
        MachineConfig(memory=MemoryConfig(total_bytes=0))
