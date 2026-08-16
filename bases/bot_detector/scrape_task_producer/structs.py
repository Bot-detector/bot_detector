from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum, auto


class ScrapeState(Enum):
    NORMAL = auto()
    POSSIBLE_BAN = auto()
    CONFIRMED_BAN = auto()
    DONE = auto()


class ScrapeEvent(Enum):
    FETCH_MORE = auto()
    REDUCE_DAYS = auto()
    NEXT_STEP = auto()
    NEW_DAY = auto()


@dataclass
class ScraperCtx:
    days: int
    limit: int
    first_date: date | None = None
    last_date: date | None = None
    confirmed_ban: bool = False
    possible_ban: bool = False
    player_id: int = 0
    last_fetched_id: int = 0

    def __post_init__(self):
        self.update_date(self.days, infinity=True)

    def update_date(self, days: int, infinity: bool = False) -> None:
        self.days = days
        delta = timedelta(days=365) if infinity else timedelta(days=self.days)
        self.first_date = date.today() - delta
        self.last_date = date.today() - timedelta(days=self.days - 1)
