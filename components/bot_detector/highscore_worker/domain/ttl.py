from datetime import timedelta
from typing import Literal

from bot_detector.structs import HighscoreBaseStruct


def set_ttl(
    data: HighscoreBaseStruct,
    table: Literal["daily", "weekly", "monthly"],
) -> HighscoreBaseStruct:
    """Apply TTL rules for the different aggregation tables."""
    mutated = data.model_copy()
    if table == "daily":
        mutated.time_to_live = mutated.scrape_date + timedelta(days=30)
    elif table == "weekly":
        mutated.time_to_live = mutated.scrape_date + timedelta(days=26 * 7)
    elif table == "monthly":
        mutated.time_to_live = mutated.scrape_date + timedelta(days=24 * 30)
    return mutated
