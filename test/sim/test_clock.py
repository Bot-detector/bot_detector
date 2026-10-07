import pytest

from dst.clock import VirtualClock


def test_default_start_is_zero():
    assert VirtualClock().time() == 0.0
    assert VirtualClock().now_s == 0.0


def test_custom_start():
    assert VirtualClock(start_s=1700000000.0).time() == 1700000000.0


def test_advance_returns_new_time_and_accumulates():
    clock = VirtualClock()
    assert clock.advance(10) == 10.0
    assert clock.advance(2.5) == 12.5
    assert clock.time() == 12.5


def test_advance_rejects_negative():
    with pytest.raises(ValueError, match="backwards"):
        VirtualClock().advance(-1)


def test_advance_rejects_non_finite():
    with pytest.raises(ValueError, match="finite"):
        VirtualClock().advance(float("nan"))
    with pytest.raises(ValueError, match="finite"):
        VirtualClock().advance(float("inf"))


def test_advance_to_jumps_forward_exactly():
    clock = VirtualClock()
    clock.advance(3)
    clock.advance_to(9.5)
    assert clock.time() == 9.5


def test_advance_to_past_is_noop():
    clock = VirtualClock()
    clock.advance(5)
    clock.advance_to(2)
    assert clock.time() == 5.0


def test_jump_counting():
    clock = VirtualClock()
    clock.advance(1)
    clock.advance(1)
    clock.advance_to(100)
    clock.advance_to(50)  # no-op: does not count
    clock.advance(0)  # zero: does not count
    assert clock.jumps == 3


def test_rejects_bad_start():
    with pytest.raises(ValueError, match="start_s"):
        VirtualClock(start_s=-0.1)
    with pytest.raises(ValueError, match="finite"):
        VirtualClock(start_s=float("inf"))
