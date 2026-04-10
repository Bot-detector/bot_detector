from bot_detector.scrape_task_producer.core import determine_event
from bot_detector.scrape_task_producer.states import (
    ScrapeEvent,
    ScraperCtx,
    ScrapeState,
    scraper_sm,
)


def make_ctx(days=20, limit=10, state=ScrapeState.NORMAL) -> ScraperCtx:
    ctx = ScraperCtx(days=days, limit=limit)
    if state == ScrapeState.POSSIBLE_BAN:
        ctx.possible_ban = True
    elif state == ScrapeState.CONFIRMED_BAN:
        ctx.possible_ban = True
        ctx.confirmed_ban = True
    return ctx


def test_fetch_more_updates_player_id_keeps_state():
    ctx = make_ctx()
    ctx.last_fetched_id = 42

    new_state = scraper_sm.handle(ctx, ScrapeState.NORMAL, ScrapeEvent.FETCH_MORE)

    assert new_state == ScrapeState.NORMAL
    assert ctx.player_id == 42
    assert ctx.days == 20


def test_reduce_days_decrements_days_resets_player_id():
    ctx = make_ctx(days=5)
    ctx.player_id = 99

    new_state = scraper_sm.handle(ctx, ScrapeState.NORMAL, ScrapeEvent.REDUCE_DAYS)

    assert new_state == ScrapeState.NORMAL
    assert ctx.days == 4
    assert ctx.player_id == 0


def test_reduce_days_floors_at_one():
    ctx = make_ctx(days=1)

    scraper_sm.handle(ctx, ScrapeState.NORMAL, ScrapeEvent.REDUCE_DAYS)

    assert ctx.days == 1


def test_next_step_normal_to_possible_ban():
    ctx = make_ctx(days=1)

    new_state = scraper_sm.handle(ctx, ScrapeState.NORMAL, ScrapeEvent.NEXT_STEP)

    assert new_state == ScrapeState.POSSIBLE_BAN
    assert ctx.possible_ban is True
    assert ctx.confirmed_ban is False
    assert ctx.days == 20  # Resets to max_days


def test_next_step_possible_ban_to_confirmed_ban():
    ctx = make_ctx(days=7, state=ScrapeState.POSSIBLE_BAN)

    new_state = scraper_sm.handle(ctx, ScrapeState.POSSIBLE_BAN, ScrapeEvent.NEXT_STEP)

    assert new_state == ScrapeState.CONFIRMED_BAN
    assert ctx.possible_ban is True
    assert ctx.confirmed_ban is True
    assert ctx.days == 20


def test_next_step_confirmed_ban_to_done():
    ctx = make_ctx(days=14, state=ScrapeState.CONFIRMED_BAN)

    new_state = scraper_sm.handle(ctx, ScrapeState.CONFIRMED_BAN, ScrapeEvent.NEXT_STEP)

    assert new_state == ScrapeState.DONE
    assert ctx.possible_ban is False
    assert ctx.confirmed_ban is False
    assert ctx.days == 20


def test_new_day_resets_to_normal():
    ctx = make_ctx(days=5, state=ScrapeState.DONE)
    ctx.player_id = 123

    new_state = scraper_sm.handle(ctx, ScrapeState.DONE, ScrapeEvent.NEW_DAY)

    assert new_state == ScrapeState.NORMAL
    assert ctx.player_id == 0
    assert ctx.days == 20
    assert ctx.possible_ban is False


# --- determine_event logic tests ---


def test_determine_event_fetch_more():
    ctx = make_ctx(limit=10)
    # 10 players returned, hit limit
    event = determine_event(ctx, ScrapeState.NORMAL, player_count=10)
    assert event == ScrapeEvent.FETCH_MORE


def test_determine_event_reduce_days_normal():
    ctx = make_ctx(days=2, limit=10)
    # 5 players returned, under limit. Days > 1 threshold for NORMAL
    event = determine_event(ctx, ScrapeState.NORMAL, player_count=5)
    assert event == ScrapeEvent.REDUCE_DAYS


def test_determine_event_next_step_normal():
    ctx = make_ctx(days=1, limit=10)
    # Days <= 1 threshold for NORMAL
    event = determine_event(ctx, ScrapeState.NORMAL, player_count=5)
    assert event == ScrapeEvent.NEXT_STEP


def test_determine_event_reduce_days_possible_ban():
    ctx = make_ctx(days=8, limit=10)
    # Days > 7 threshold for POSSIBLE_BAN
    event = determine_event(ctx, ScrapeState.POSSIBLE_BAN, player_count=0)
    assert event == ScrapeEvent.REDUCE_DAYS


def test_determine_event_next_step_possible_ban():
    ctx = make_ctx(days=7, limit=10)
    # Days <= 7 threshold for POSSIBLE_BAN
    event = determine_event(ctx, ScrapeState.POSSIBLE_BAN, player_count=0)
    assert event == ScrapeEvent.NEXT_STEP
