import logging
from datetime import date, datetime, timedelta

from aiohttp import ClientSession
from bot_detector.event_queue.structs import ScrapedStruct
from bot_detector.hiscore_scraper.scraping.metrics import (
    fetch_outcome_latency_histogram,
    latency_histogram,
)
from bot_detector.osrs_hs_api import HiscoreOldSchoolAPI
from bot_detector.osrs_hs_api.exceptions import Err, Ok, PlayerDoesNotExist
from bot_detector.osrs_hs_api.structs import PlayerStats
from bot_detector.structs import HighscoreBaseStruct, MetaData, PlayerStruct
from pydantic import ValidationError

logger = logging.getLogger(__name__)


def proxy_label(proxy: str) -> str:
    """Host:port of a proxy URL, without credentials."""
    if "@" in proxy:
        return proxy.split("@", 1)[1]
    return proxy


async def scrape_player(
    player: PlayerStruct,
    session: ClientSession,
    api: HiscoreOldSchoolAPI,
    proxy: str,
) -> tuple[PlayerStats | None, Exception | None]:
    """Scrapes player stats; caller handles retry, not_found and proxy refresh."""
    result = await api.get(player=player.name, session=session, proxy=proxy)

    if isinstance(result, Ok):
        latency_histogram.labels(proxy=proxy).observe(result.latency)
        fetch_outcome_latency_histogram.labels(
            proxy=proxy_label(proxy), outcome="success"
        ).observe(result.latency)
        return result.value, None
    elif isinstance(result, Err):
        if result.latency > 0:
            outcome = (
                "not_found" if isinstance(result.error, PlayerDoesNotExist) else "error"
            )
            fetch_outcome_latency_histogram.labels(
                proxy=proxy_label(proxy), outcome=outcome
            ).observe(result.latency)
        return None, result.error
    else:
        return None, Exception("Unexpected result type from scrape_player")


async def transform_player_stats(
    player_stats: PlayerStats,
    player: PlayerStruct,
) -> ScrapedStruct | None:
    player.updated_at = datetime.now()
    player.possible_ban = False
    player.confirmed_ban = False
    player.label_jagex = 0

    skills = {s.name: s.xp for s in player_stats.skills if s.xp > 0}
    activities = {a.name: a.score for a in player_stats.activities if a.score > 0}

    try:
        return ScrapedStruct(
            metadata=MetaData(version=1, source="hiscore_scraper"),
            player_data=player,
            highscore_data=HighscoreBaseStruct(
                player_id=player.id,
                scrape_date=date.today(),
                skills=skills,
                activities=activities,
                time_to_live=date.today() + timedelta(days=30),
            ),
        )
    except ValidationError as e:
        # the processor owns the requeue; it turns None into a
        # produce_player_to_scrape side effect
        logger.error(e.json())
        return None
