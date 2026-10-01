"""VirtualEventLoop behavior: unmodified asyncio code on virtual time."""

import asyncio
import time

import pytest

from dst.clock import VirtualClock
from dst.loop import DSTIdleError, VirtualEventLoop


@pytest.fixture
def clock() -> VirtualClock:
    return VirtualClock()


@pytest.fixture
def loop(clock: VirtualClock) -> VirtualEventLoop:
    return VirtualEventLoop(clock)


def test_sleep_resolves_in_virtual_time(loop: VirtualEventLoop):
    async def main() -> float:
        t0 = loop.time()
        await asyncio.sleep(30)
        return loop.time() - t0

    wall_t0 = time.perf_counter()
    elapsed = loop.run_until_complete(main())
    wall_s = time.perf_counter() - wall_t0

    assert elapsed == pytest.approx(30.0)
    assert loop.clock.time() == pytest.approx(30.0)
    assert wall_s < 1.0


def test_sleep_year_is_one_wall_second(loop: VirtualEventLoop):
    async def main() -> None:
        for _ in range(365):
            await asyncio.sleep(86400)

    wall_t0 = time.perf_counter()
    loop.run_until_complete(main())

    assert loop.clock.time() == pytest.approx(365 * 86400)
    assert time.perf_counter() - wall_t0 < 1.0


def test_timers_fire_in_deadline_order(loop: VirtualEventLoop):
    fired: list[float] = []
    loop.call_later(10, fired.append, 10.0)
    loop.call_later(5, fired.append, 5.0)
    loop.call_later(5, fired.append, 5.1)

    async def main() -> None:
        await asyncio.sleep(11)

    loop.run_until_complete(main())
    assert fired == [5.0, 5.1, 10.0]
    assert loop.clock.time() == pytest.approx(11.0)


def test_call_at_uses_virtual_deadline(loop: VirtualEventLoop):
    fired: list[float] = []
    loop.call_at(1000, fired.append, loop.time())

    async def main() -> None:
        await asyncio.sleep(1000)

    loop.run_until_complete(main())
    assert fired == [0.0]
    assert loop.clock.time() == pytest.approx(1000.0)


def test_wait_for_times_out_on_virtual_time(loop: VirtualEventLoop):
    async def main() -> None:
        event = asyncio.Event()
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(event.wait(), timeout=7.5)
        assert loop.time() == pytest.approx(7.5)

    loop.run_until_complete(main())


def test_wait_for_passes_before_timeout(loop: VirtualEventLoop):
    async def main() -> float:
        event = asyncio.Event()

        async def setter() -> None:
            await asyncio.sleep(2)
            event.set()

        t0 = loop.time()
        await asyncio.wait_for(setter(), timeout=5)
        return loop.time() - t0

    assert loop.run_until_complete(main()) == pytest.approx(2.0)


def test_idle_loop_raises_dst_idle_error(loop: VirtualEventLoop):
    async def main() -> None:
        await asyncio.Event().wait()  # nobody will ever set it

    with pytest.raises(DSTIdleError, match="idle"):
        loop.run_until_complete(main())


def test_queue_handoff_between_tasks(loop: VirtualEventLoop):
    async def main() -> list[int]:
        queue: asyncio.Queue[int] = asyncio.Queue(maxsize=2)
        received: list[int] = []

        async def producer() -> None:
            for i in range(6):
                await queue.put(i)

        async def consumer() -> None:
            for _ in range(6):
                await asyncio.sleep(0.5)
                received.append(await queue.get())

        await asyncio.gather(producer(), consumer())
        return received

    assert loop.run_until_complete(main()) == [0, 1, 2, 3, 4, 5]
    assert loop.clock.time() == pytest.approx(3.0)


def test_concurrent_tasks_interleave_on_virtual_time(loop: VirtualEventLoop):
    async def worker(name: str, delay: float, log: list[str]) -> None:
        for _ in range(3):
            await asyncio.sleep(delay)
            log.append(name)

    async def main() -> list[str]:
        log: list[str] = []
        await asyncio.gather(worker("fast", 1, log), worker("slow", 1.7, log))
        return log

    assert loop.run_until_complete(main()) == [
        "fast",
        "slow",
        "fast",
        "fast",
        "slow",
        "slow",
    ]
    assert loop.clock.time() == pytest.approx(5.1)


def test_sleep_zero_does_not_advance(loop: VirtualEventLoop):
    async def main() -> None:
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    loop.run_until_complete(main())
    assert loop.clock.time() == 0.0


def test_cancelled_timer_never_fires(loop: VirtualEventLoop):
    fired: list[str] = []
    handle = loop.call_later(5, fired.append, "never")
    handle.cancel()

    async def main() -> None:
        await asyncio.sleep(10)

    loop.run_until_complete(main())
    assert fired == []
    assert loop.clock.time() == pytest.approx(10.0)


def test_exception_handler_receives_callback_error(
    loop: VirtualEventLoop, clock: VirtualClock
):
    seen: list[BaseException] = []
    loop.set_exception_handler(lambda _loop, ctx: seen.append(ctx["exception"]))

    def boom() -> None:
        raise RuntimeError("callback blew up")

    loop.call_later(1, boom)

    async def main() -> None:
        await asyncio.sleep(2)

    loop.run_until_complete(main())
    assert isinstance(seen[0], RuntimeError)
    assert str(seen[0]) == "callback blew up"
    assert clock.time() == pytest.approx(2.0)
