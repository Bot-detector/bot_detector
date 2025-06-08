# bases/bot_detector/api_private/test/api/v3/test_highscore_unit.py
from datetime import datetime

from bot_detector.api_private.src.api.v3.highscore import (
    ActivityView,
    SkillView,
    convert_to_scraper_data_view,
)


def test_convert_groups_rows_by_scraper_id():
    # -- Arrange -----------------------------------------------------------------
    sample_rows = [
        {
            "scrape_id": 1,
            "scrape_ts": datetime(2025, 6, 7, 12, 0),
            "scrape_date": datetime(2025, 6, 7).date(),
            "player_id": 99,
            "player_name": "Bob",
            "hs_type": "skill",
            "hs_name": "strength",
            "hs_value": 42,
        },
        {
            "scrape_id": 1,
            "scrape_ts": datetime(2025, 6, 7, 12, 0),
            "scrape_date": datetime(2025, 6, 7).date(),
            "player_id": 99,
            "player_name": "Bob",
            "hs_type": "activity",
            "hs_name": "clue-scroll",
            "hs_value": 100,
        },
    ]

    # -- Act ---------------------------------------------------------------------
    result = convert_to_scraper_data_view(sample_rows)

    # -- Assert ------------------------------------------------------------------
    assert len(result) == 1  # rows collapsed into one ScraperDataView
    view = result[0]
    assert view.scraper_id == 1
    assert view.player_name == "Bob"
    assert view.skills == [SkillView(skill_name="strength", skill_value=42)]
    assert view.activities == [
        ActivityView(activity_name="clue-scroll", activity_value=100)
    ]
