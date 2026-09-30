import pytest

from development.perf.firehose.events import EventInjector, EventSchedule


def test_injector_same_seed_same_stream():
    schedule = EventSchedule(seed=42, error_pct=5.0, poison_pct=10.0)
    a = EventInjector(schedule)
    b = EventInjector(schedule)

    stream_a = [a.next_event() for _ in range(1000)]
    stream_b = [b.next_event() for _ in range(1000)]

    assert stream_a == stream_b


def test_injector_different_seeds_differ():
    a = EventInjector(EventSchedule(seed=1, error_pct=30.0, poison_pct=30.0))
    b = EventInjector(EventSchedule(seed=2, error_pct=30.0, poison_pct=30.0))

    stream_a = [a.next_event() for _ in range(200)]
    stream_b = [b.next_event() for _ in range(200)]

    assert stream_a != stream_b


def test_injector_zero_pct_never_injects():
    injector = EventInjector(EventSchedule(seed=7))

    stream = [injector.next_event() for _ in range(500)]

    assert set(stream) == {None}
    assert injector.errors == 0
    assert injector.poisons == 0


def test_injector_full_error_pct_injects_only_errors():
    injector = EventInjector(EventSchedule(seed=3, error_pct=100.0))

    stream = [injector.next_event() for _ in range(50)]

    assert set(stream) == {"error"}


def test_injector_counts_match_stream():
    injector = EventInjector(EventSchedule(seed=11, error_pct=40.0, poison_pct=40.0))

    stream = [injector.next_event() for _ in range(300)]

    assert injector.errors == stream.count("error")
    assert injector.poisons == stream.count("poison")
    assert injector.draws == 300


def test_injector_rejects_schedule_over_100_pct():
    with pytest.raises(ValueError, match="must be <= 100"):
        EventInjector(EventSchedule(seed=0, error_pct=60.0, poison_pct=60.0))
