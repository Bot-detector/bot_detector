from datetime import date

from bot_detector.api_private.src.api.v4.highscore import (
    ActivityView,
    SkillView,
    convert_latest_struct_to_scraper_data_view,
)
from bot_detector.structs import HighscoreDataLatestStruct


def test_convert_single_struct_to_scraper_data_view():
    # -- Arrange -----------------------------------------------------------------
    sample_rows = [
        HighscoreDataLatestStruct(
            player_id=99,
            player_name="Bob",
            scrape_date=date(2025, 6, 7),
            skills={"strength": 42},
            activities={"clue-scroll": 100},
            time_to_live=date(2025, 6, 30),
            scrape_year=2025,
            scrape_month=6,
            scrape_week=23,
        )
    ]

    # -- Act ---------------------------------------------------------------------
    result = convert_latest_struct_to_scraper_data_view(sample_rows)

    # -- Assert ------------------------------------------------------------------
    assert len(result) == 1
    view = result[0]
    assert view.scraper_id == 99
    assert view.player_name == "Bob"
    assert view.skills == [SkillView(skill_name="strength", skill_value=42)]
    assert view.activities == [ActivityView(activity_name="clue-scroll", activity_value=100)]


def test_convert_multiple_structs_to_scraper_data_view():
    # -- Arrange -----------------------------------------------------------------
    sample_rows = [
        HighscoreDataLatestStruct(
            player_id=99,
            player_name="Bob",
            scrape_date=date(2025, 6, 7),
            skills={"strength": 42},
            activities={"clue-scroll": 100},
            time_to_live=date(2025, 6, 30),
            scrape_year=2025,
            scrape_month=6,
            scrape_week=23,
        ),
        HighscoreDataLatestStruct(
            player_id=100,
            player_name="Alice",
            scrape_date=date(2025, 6, 8),
            skills={"attack": 35},
            activities={"barrows": 200},
            time_to_live=date(2025, 6, 30),
            scrape_year=2025,
            scrape_month=6,
            scrape_week=23,
        ),
    ]

    # -- Act ---------------------------------------------------------------------
    result = convert_latest_struct_to_scraper_data_view(sample_rows)

    # -- Assert ------------------------------------------------------------------
    assert len(result) == 2

    view0 = result[0]
    assert view0.scraper_id == 99
    assert view0.player_name == "Bob"
    assert view0.skills == [SkillView(skill_name="strength", skill_value=42)]
    assert view0.activities == [ActivityView(activity_name="clue-scroll", activity_value=100)]

    view1 = result[1]
    assert view1.scraper_id == 100
    assert view1.player_name == "Alice"
    assert view1.skills == [SkillView(skill_name="attack", skill_value=35)]
    assert view1.activities == [ActivityView(activity_name="barrows", activity_value=200)]
