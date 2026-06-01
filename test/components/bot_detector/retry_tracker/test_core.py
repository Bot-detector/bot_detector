import time

from bot_detector.retry_tracker import RetryTracker


def test_initial_backoff_delay_is_near_base():
    tracker = RetryTracker(base_delay=10.0, jitter_factor=0.0)
    delay = tracker.get_backoff_delay(worker_id=0)
    assert delay == 10.0


def test_exponential_growth_on_failures():
    tracker = RetryTracker(base_delay=10.0, max_delay=300.0, jitter_factor=0.0)
    tracker.record_attempt(worker_id=0, success=False)
    delay = tracker.get_backoff_delay(worker_id=0)
    assert delay == 20.0

    tracker.record_attempt(worker_id=0, success=False)
    delay = tracker.get_backoff_delay(worker_id=0)
    assert delay == 40.0


def test_max_delay_cap():
    tracker = RetryTracker(base_delay=10.0, max_delay=60.0, jitter_factor=0.0)
    for _ in range(10):
        tracker.record_attempt(worker_id=0, success=False)
    delay = tracker.get_backoff_delay(worker_id=0)
    assert delay == 60.0


def test_jitter_range():
    tracker = RetryTracker(base_delay=10.0, max_delay=300.0, jitter_factor=0.5)
    tracker.record_attempt(worker_id=0, success=False)
    for _ in range(100):
        delay = tracker.get_backoff_delay(worker_id=0)
        assert 10.0 <= delay <= 30.0


def test_success_resets_counter():
    tracker = RetryTracker(base_delay=10.0, max_delay=300.0, jitter_factor=0.0)
    tracker.record_attempt(worker_id=0, success=False)
    tracker.record_attempt(worker_id=0, success=False)
    tracker.record_attempt(worker_id=0, success=True)
    delay = tracker.get_backoff_delay(worker_id=0)
    assert delay == 10.0


def test_time_decay_resets_failures():
    tracker = RetryTracker(
        base_delay=10.0, max_delay=300.0, decay_window=1.0, jitter_factor=0.0
    )
    tracker.record_attempt(worker_id=0, success=False)
    tracker.record_attempt(worker_id=0, success=False)
    assert tracker.get_retry_count(worker_id=0) == 2
    time.sleep(1.1)
    delay = tracker.get_backoff_delay(worker_id=0)
    assert delay == 10.0
    assert tracker.get_retry_count(worker_id=0) == 0


def test_per_worker_isolation():
    tracker = RetryTracker(base_delay=10.0, max_delay=300.0, jitter_factor=0.0)
    tracker.record_attempt(worker_id=0, success=False)
    tracker.record_attempt(worker_id=0, success=False)
    delay_w0 = tracker.get_backoff_delay(worker_id=0)
    delay_w1 = tracker.get_backoff_delay(worker_id=1)
    assert delay_w0 == 40.0
    assert delay_w1 == 10.0


def test_get_retry_count_with_decay():
    tracker = RetryTracker(decay_window=1.0)
    tracker.record_attempt(worker_id=0, success=False)
    tracker.record_attempt(worker_id=0, success=False)
    assert tracker.get_retry_count(worker_id=0) == 2
    time.sleep(1.1)
    assert tracker.get_retry_count(worker_id=0) == 0


def test_minimum_delay_clamp():
    tracker = RetryTracker(base_delay=0.1, max_delay=300.0, jitter_factor=0.0)
    delay = tracker.get_backoff_delay(worker_id=0)
    assert delay >= 1.0
