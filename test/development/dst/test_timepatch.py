"""Sync time patching: blocking legacy code on the virtual clock."""

import time

import pytest

from dst import VirtualClock, run, virtual_time


def test_time_functions_read_virtual_time():
    clock = VirtualClock(start_s=42)
    with virtual_time(clock):
        assert time.time() == 42.0
        assert time.monotonic() == 42.0
        assert time.perf_counter() == 42.0
        assert time.time_ns() == 42_000_000_000
        assert time.monotonic_ns() == 42_000_000_000
        assert time.perf_counter_ns() == 42_000_000_000


def test_sleep_advances_clock_and_returns_immediately():
    clock = VirtualClock()
    wall_t0 = time.perf_counter()
    with virtual_time(clock):
        time.sleep(3600)
        assert clock.time() == 3600.0
    assert time.perf_counter() - wall_t0 < 1.0


def test_state_is_restored_after_block():
    real_time = time.time()
    real_sleep = time.sleep
    clock = VirtualClock()
    with virtual_time(clock):
        assert time.sleep is not real_sleep
    assert time.time() >= real_time
    assert time.sleep is real_sleep


def test_negative_sleep_rejected():
    with virtual_time(VirtualClock()):
        with pytest.raises(ValueError, match="non-negative"):
            time.sleep(-1)


def test_nesting_rejected():
    with virtual_time(VirtualClock()):
        with pytest.raises(RuntimeError, match="nested"):
            with virtual_time(VirtualClock()):
                pass


def test_patch_inside_dst_scenario():
    async def scenario() -> float:
        with virtual_time():
            time.sleep(5)
            return time.monotonic()

    result = run(scenario())
    assert result.done is True
    assert result.virtual_time_s == pytest.approx(5.0)
