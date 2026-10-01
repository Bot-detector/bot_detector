"""Scenario runner: drive coroutines on the virtual loop and report.

``run()`` is the DST entry point for one scenario:

    result = dst.run(scenario(), until_s=3600)
    assert result.done
    assert result.virtual_time_s == 3600

The run is wall-clock fast: a simulated day of sleeps, timeouts and
queued handoffs finishes in milliseconds. Wall time of the scenario is
recorded so scenarios can double as micro-benchmarks.
"""

import asyncio
import time
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import Any

from .clock import VirtualClock
from .loop import DSTIdleError, VirtualEventLoop


@dataclass
class SimResult:
    """Outcome of one simulated scenario run.

    done: the scenario coroutine reached completion
    value: the scenario's return value (None unless done)
    error: exception raised by the scenario, or the DSTIdleError that
        aborted a scenario parked on something that never fires
    pending_tasks: tasks still alive when the run ended (empty when
        done is True)
    """

    virtual_time_s: float
    wall_time_s: float
    done: bool
    value: Any = None
    error: BaseException | None = None
    pending_tasks: list[str] = field(default_factory=list)


def run(
    scenario: Coroutine[Any, Any, Any],
    *,
    start_s: float = 0.0,
    until_s: float | None = None,
) -> SimResult:
    """Run ``scenario`` on a fresh virtual loop and return the outcome.

    until_s: stop once virtual time reaches this deadline even if the
        scenario is still running (for "what does the system look like
        after N seconds" scenarios); pending tasks are reported and
        cancelled.
    """
    clock = VirtualClock(start_s=start_s)
    loop = VirtualEventLoop(clock)
    error: BaseException | None = None
    value: Any = None
    done = False
    pending: list[asyncio.Task[Any]] = []
    wall_t0 = time.monotonic()
    try:
        asyncio.set_event_loop(loop)
        main_task = loop.create_task(scenario)
        main_task.add_done_callback(lambda _task: loop.stop())
        deadline = loop.call_at(until_s, loop.stop) if until_s is not None else None
        try:
            loop.run_forever()
        except DSTIdleError as exc:
            error = exc
        wall_s = time.monotonic() - wall_t0
        if main_task.done() and not main_task.cancelled():
            done = True
            error = main_task.exception()
            if error is None:
                value = main_task.result()
        if deadline is not None:
            deadline.cancel()
        pending = [
            t for t in asyncio.all_tasks(loop) if t is not main_task and not t.done()
        ]
        # the scenario itself stays pending on idle/until stops; cancel
        # everything so close() is clean, but only report leaked children
        cancel_targets = [t for t in asyncio.all_tasks(loop) if not t.done()]
        for task in cancel_targets:
            task.cancel()
        if cancel_targets:
            loop.run_until_complete(
                asyncio.gather(*cancel_targets, return_exceptions=True)
            )
    finally:
        asyncio.set_event_loop(None)
        loop.close()
    return SimResult(
        virtual_time_s=clock.time(),
        wall_time_s=wall_s,
        done=done,
        value=value,
        error=error,
        pending_tasks=[f"{t.get_name()}: {t.get_coro()}" for t in pending],
    )
