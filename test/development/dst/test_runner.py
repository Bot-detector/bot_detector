"""Runner scenarios: SimResult fields, deadlines, idle detection."""

import asyncio
import time

import pytest

import dst as dst
from dst import SimResult
from dst.loop import DSTIdleError


def test_completed_scenario_reports_virtual_time():
    async def scenario() -> str:
        await asyncio.sleep(30)
        return "ok"

    wall_t0 = time.perf_counter()
    result = dst.run(scenario())
    wall_s = time.perf_counter() - wall_t0

    assert result == SimResult(
        virtual_time_s=30.0,
        wall_time_s=result.wall_time_s,
        done=True,
        value="ok",
        error=None,
        pending_tasks=[],
    )
    assert result.wall_time_s < 1.0
    assert wall_s < 1.0


def test_scenario_exception_is_captured_as_value():
    async def scenario() -> None:
        await asyncio.sleep(1)
        raise ValueError("scenario failed")

    result = dst.run(scenario())

    assert result.done is True
    assert isinstance(result.error, ValueError)
    assert str(result.error) == "scenario failed"
    assert result.pending_tasks == []


def test_until_s_stops_before_completion():
    async def scenario() -> None:
        await asyncio.sleep(100)

    result = dst.run(scenario(), until_s=10)

    assert result.done is False
    assert result.error is None
    assert result.virtual_time_s == pytest.approx(10.0)
    assert result.pending_tasks == []  # main scenario is not leaked children


def test_idle_scenario_reports_dst_idle_error():
    async def scenario() -> None:
        await asyncio.Event().wait()

    result = dst.run(scenario())

    assert result.done is False
    assert isinstance(result.error, DSTIdleError)
    assert result.virtual_time_s == 0.0
    assert result.pending_tasks == []


def test_start_s_offsets_the_timeline():
    async def scenario() -> None:
        await asyncio.sleep(5)

    result = dst.run(scenario(), start_s=1000)

    assert result.virtual_time_s == pytest.approx(1005.0)


def test_same_scenario_produces_same_virtual_timeline():
    async def scenario() -> list[float]:
        stamps = []
        for _ in range(5):
            await asyncio.sleep(7)
            stamps.append(asyncio.get_running_loop().time())
        return stamps

    result_a = dst.run(scenario())
    result_b = dst.run(scenario())

    assert result_a.done and result_b.done
    assert result_a.virtual_time_s == result_b.virtual_time_s == pytest.approx(35.0)


def test_pending_task_names_are_descriptive():
    async def background() -> None:
        await asyncio.sleep(50)

    async def scenario() -> None:
        asyncio.get_running_loop().create_task(background(), name="sim-bg")
        await asyncio.sleep(10)

    result = dst.run(scenario(), until_s=10)

    assert result.done is False
    assert len(result.pending_tasks) == 1
    assert "sim-bg" in result.pending_tasks[0]
