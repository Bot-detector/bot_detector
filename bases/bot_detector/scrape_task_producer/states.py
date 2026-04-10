from dataclasses import asdict

from bot_detector.scrape_task_producer.sm import StateMachine
from bot_detector.wide_event import WideEventLogger

from .structs import ScrapeEvent, ScraperCtx, ScrapeState

wide_event = WideEventLogger()


scraper_sm = StateMachine[ScrapeState, ScrapeEvent, ScraperCtx]()
ALL = (ScrapeState.NORMAL, ScrapeState.POSSIBLE_BAN, ScrapeState.CONFIRMED_BAN)


# fmt: off
@scraper_sm.transition(from_state=ALL, event=ScrapeEvent.FETCH_MORE, to_state=ScrapeState.NORMAL)
@scraper_sm.transition(from_state=ALL, event=ScrapeEvent.FETCH_MORE, to_state=ScrapeState.POSSIBLE_BAN)
@scraper_sm.transition(from_state=ALL, event=ScrapeEvent.FETCH_MORE,to_state=ScrapeState.CONFIRMED_BAN)
# fmt: on
def fetch_more(ctx: ScraperCtx) -> None:
    # Hack to keep same state: manually set to_state per from_state.
    # Decorator maps explicitly above, but engine needs exact to_state.
    # Alternative: return state from action.
    # Here, engine updates state. We just update context.
    ctx.player_id = ctx.last_fetched_id

# fmt: off
@scraper_sm.transition(from_state=ScrapeState.NORMAL, event=ScrapeEvent.REDUCE_DAYS, to_state=ScrapeState.NORMAL)
@scraper_sm.transition(from_state=ScrapeState.POSSIBLE_BAN, event=ScrapeEvent.REDUCE_DAYS, to_state=ScrapeState.POSSIBLE_BAN)
@scraper_sm.transition(from_state=ScrapeState.CONFIRMED_BAN, event=ScrapeEvent.REDUCE_DAYS, to_state=ScrapeState.CONFIRMED_BAN)
# fmt: on
def reduce_days(ctx: ScraperCtx) -> None:
    wide_event.add({"reduce_days": {"fetch_params": asdict(ctx)}})
    _days = ctx.days - 1 if ctx.days > 1 else 1
    ctx.update_date(days=_days, infinity=False)
    ctx.player_id = 0

def _force_log() -> None:
    wide_event.add({"force_log": True})

# fmt: off
@scraper_sm.transition(ScrapeState.NORMAL, ScrapeEvent.NEXT_STEP, ScrapeState.POSSIBLE_BAN)
# fmt: on
def to_possible_ban(ctx: ScraperCtx) -> None:
    wide_event.add({"set_step": {"from": "normal", "to": "possible_ban"}})
    _force_log()
    ctx.possible_ban = True
    ctx.confirmed_ban = False
    ctx.update_date(days=20, infinity=True)

# fmt: off
@scraper_sm.transition(ScrapeState.POSSIBLE_BAN, ScrapeEvent.NEXT_STEP, ScrapeState.CONFIRMED_BAN)
# fmt: on
def to_confirmed_ban(ctx: ScraperCtx) -> None:
    wide_event.add({"set_step": {"from": "possible_ban", "to": "confirmed_ban"}})
    _force_log()
    ctx.possible_ban = True
    ctx.confirmed_ban = True
    ctx.update_date(days=20, infinity=True)

# fmt: off
@scraper_sm.transition(ScrapeState.CONFIRMED_BAN, ScrapeEvent.NEXT_STEP, ScrapeState.DONE)
# fmt: on
def to_done(ctx: ScraperCtx) -> None:
    wide_event.add({"set_step": {"from": "confirmed_ban", "to": "done"}})
    _force_log()
    ctx.possible_ban = False
    ctx.confirmed_ban = False
    ctx.update_date(days=20, infinity=True)

# fmt: off
@scraper_sm.transition((ScrapeState.DONE, ScrapeState.NORMAL), ScrapeEvent.NEW_DAY, ScrapeState.NORMAL)
# fmt: on
def reset_new_day(ctx: ScraperCtx) -> None:
    wide_event.add({"new_day_reset": True})
    _force_log()
    ctx.possible_ban = False
    ctx.confirmed_ban = False
    ctx.player_id = 0
    ctx.update_date(days=20, infinity=True)
