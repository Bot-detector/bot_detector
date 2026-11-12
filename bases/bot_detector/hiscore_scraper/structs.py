from dataclasses import dataclass

from bot_detector.osrs_hs_api.structs import PlayerStats
from bot_detector.structs import PlayerStruct


@dataclass(frozen=True, slots=True)
class FetchResult:
    """Outcome of one fetch, carried from the fetch pool to a processor.

    The proxy label rides along because fetch-stage identity (who
    scraped) is decoupled from processing identity once the stages are
    split into separate coroutines.
    """

    player: PlayerStruct
    proxy: str
    stats: PlayerStats | None = None
    error: Exception | None = None
