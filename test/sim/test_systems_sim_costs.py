import asyncio
import math

import pytest

from dst.systems.sim_costs import CpuCosts, LinkCosts, LinkError


def run(coro):
    return asyncio.run(coro)


def make_link(**kwargs) -> LinkCosts:
    base = {"seed": 42, "stream": "test:link"}
    base.update(kwargs)
    return LinkCosts(**base)


# --- determinism --------------------------------------------------------


def test_link_draws_deterministic_per_seed():
    first = make_link(seed=7, mean_ms=5.0, jitter_ms=2.0)
    second = make_link(seed=7, mean_ms=5.0, jitter_ms=2.0)
    a = [first.draw(0) for _ in range(20)]
    b = [second.draw(0) for _ in range(20)]
    assert a == b  # same (seed, stream, ordinal) => same draws forever


def test_link_draw_order_is_free():
    # counter-based draws: interleaving two links never shifts either
    baseline = make_link(seed=7)
    solo = [baseline.draw(0)[0] for _ in range(10)]
    one = make_link(seed=7)
    two = make_link(seed=7)
    interleaved = []
    for i in range(10):
        interleaved.append(one.draw(0)[0] if i % 2 == 0 else two.draw(0)[0])
    # one drew on the even i's: those are its ordinals 0..4
    assert interleaved[0::2] == solo[:5]
    # two is untouched by one's draws (same ordinals, same stream+seed)
    assert [two.draw(0)[0] for _ in range(5)] == solo[5:10]


def test_link_different_seed_usually_draws_differently():
    a = make_link(seed=1, mean_ms=100.0, jitter_ms=50.0)
    b = make_link(seed=2, mean_ms=100.0, jitter_ms=50.0)
    seq_a = [a.draw(0)[0] for _ in range(20)]
    seq_b = [b.draw(0)[0] for _ in range(20)]
    assert seq_a != seq_b  # deterministic given the fixed seeds above


# --- bound behavior -----------------------------------------------------


def test_link_latency_stays_within_jitter_bounds():
    link = make_link(mean_ms=10.0, jitter_ms=4.0)
    latencies = [link.draw(0)[0] for _ in range(200)]
    assert all(6.0 / 1000 <= d <= 14.0 / 1000 for d in latencies)
    assert link.calls == 0  # draw() never sleeps or counts a fetch


def test_link_zero_jitter_is_exact_mean():
    link = make_link(mean_ms=3.0, jitter_ms=0.0)
    for _ in range(5):
        latency_s, _error = link.draw(0)
        assert latency_s == pytest.approx(0.003)


def test_link_clamps_negative_latency_at_zero():
    link = make_link(mean_ms=0.0, jitter_ms=1.0)
    latencies = [link.draw(0)[0] for _ in range(200)]
    assert all(d >= 0.0 for d in latencies)
    assert min(latencies) == 0.0  # the negative half clamps, not wraps


def test_link_bandwidth_adds_exact_transfer_time():
    link = make_link(mean_ms=0.0, jitter_ms=0.0, bandwidth_mbps=8.0)  # 1 MB/s
    latency_s, _error = link.draw(1_000_000)
    assert latency_s == pytest.approx(1.0, rel=1e-9)  # 8 Mbit at 8 Mbps


def test_link_bandwidth_skips_zero_byte_fetches():
    link = make_link(mean_ms=0.0, jitter_ms=0.0, bandwidth_mbps=8.0)
    latency_s, _error = link.draw(0)
    assert latency_s == 0.0  # no bytes, no transfer time


def test_link_huge_transfer_scales_linearly():
    link = make_link(mean_ms=0.0, jitter_ms=0.0, bandwidth_mbps=800.0)
    small, _e = link.draw(512)
    big, _e2 = link.draw(512 * 1000)
    assert big == pytest.approx(small * 1000, rel=1e-9)


# --- fault-knob negative space -----------------------------------------


def test_link_zero_loss_pct_never_faults():
    link = make_link(loss_pct=0.0)
    for _ in range(500):
        _latency_s, error = link.draw(0)
        assert error is None
    assert link.failures == 0


def test_link_full_loss_pct_faults_every_fetch():
    link = make_link(loss_pct=100.0)
    errors = []
    for _ in range(20):
        _latency_s, error = link.draw(0)
        errors.append(error)
    assert all(isinstance(e, LinkError) for e in errors)
    assert all("lost" in str(e) for e in errors)


def test_link_loss_still_pays_latency():
    link = make_link(mean_ms=2.0, jitter_ms=0.0, loss_pct=100.0)
    latency_s, error = link.draw(0)
    assert isinstance(error, LinkError)
    assert latency_s == pytest.approx(0.002)  # the RTT elapses either way


async def _fetch_and_count(link: LinkCosts, n: int) -> tuple[int, int]:
    failures = 0
    for _ in range(n):
        if await link.fetch(0) is not None:
            failures += 1
    return link.calls, failures


def test_link_fetch_counts_calls_and_failures():
    clean = make_link(loss_pct=0.0)
    calls, failures = run(_fetch_and_count(clean, 10))
    assert (calls, failures) == (10, 0)
    lossy = make_link(loss_pct=100.0)
    calls, failures = run(_fetch_and_count(lossy, 10))
    assert (calls, failures) == (10, 10)
    assert lossy.latency_s >= 0.0 and clean.latency_s >= 0.0


def test_link_fetch_rejects_negative_bytes():
    link = make_link()
    with pytest.raises(ValueError, match=">= 0"):
        run(link.fetch(-1))


# --- knob validation ----------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"mean_ms": -0.1},
        {"mean_ms": float("nan")},
        {"mean_ms": float("inf")},
        {"jitter_ms": -1.0},
        {"jitter_ms": float("nan")},
        {"bandwidth_mbps": 0.0},
        {"bandwidth_mbps": -5.0},
        {"bandwidth_mbps": float("inf")},
        {"loss_pct": -0.1},
        {"loss_pct": 100.5},
        {"loss_pct": float("nan")},
    ],
)
def test_link_rejects_invalid_knobs(kwargs):
    with pytest.raises(ValueError):
        make_link(**kwargs)


def test_link_requires_a_stream_name():
    with pytest.raises(AssertionError, match="stream"):
        make_link(stream="")
    with pytest.raises(AssertionError, match="stream"):
        make_link(stream=None)  # type: ignore[arg-type]


# --- CpuCosts -----------------------------------------------------------


def test_cpu_work_counts_every_call_and_busy_total():
    async def scenario() -> tuple[int, float]:
        cpu = CpuCosts()
        await cpu.work(0.5)
        await cpu.work(0.25)
        await cpu.work(0.0)  # free calls still count
        return cpu.calls, cpu.busy_s

    calls, busy_s = run(scenario())
    assert calls == 3
    assert busy_s == pytest.approx(0.75)


def test_cpu_zero_cost_does_not_yield_to_the_loop():
    async def scenario() -> int:
        cpu = CpuCosts()
        before = asyncio.all_tasks()
        await cpu.work(0.0)
        return len(asyncio.all_tasks() - before)

    assert run(scenario()) == 0  # no sleep scheduled


def test_cpu_work_rejects_bad_costs():
    cpu = CpuCosts()

    async def bad(value: float) -> None:
        await cpu.work(value)

    with pytest.raises(ValueError, match="finite"):
        run(bad(float("nan")))
    with pytest.raises(ValueError, match="finite"):
        run(bad(float("inf")))
    with pytest.raises(ValueError, match=">= 0"):
        run(bad(-0.5))
    assert cpu.calls == 0 and cpu.busy_s == 0.0  # rejected before counting


def test_cpu_many_works_terminate():
    async def scenario() -> float:
        cpu = CpuCosts()
        total_s = 0.0
        for _ in range(1000):  # bounded loop: every iteration terminates
            await cpu.work(0.001)
            total_s += 0.001
        assert cpu.busy_s == pytest.approx(total_s)
        return cpu.busy_s

    assert run(scenario()) == pytest.approx(1.0)
    assert math.isfinite(run(scenario()))
