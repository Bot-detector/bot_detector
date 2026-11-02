from datetime import UTC, date, datetime

import pytest
from bot_detector.event_queue.structs import ScrapedStruct
from bot_detector.structs import HighscoreBaseStruct, MetaData, PlayerStruct
from bot_detector.worker_hiscore import adapter


@pytest.fixture
def scraped_jagex_names() -> ScrapedStruct:
    """ScrapedStruct with keys exactly as jagex returns them in index_lite.json."""
    return ScrapedStruct(
        metadata=MetaData(version=1, source="hiscore_scraper"),
        player_data=PlayerStruct(
            id=123,
            name="tester",
            created_at=datetime.now(tz=UTC),
        ),
        highscore_data=HighscoreBaseStruct(
            player_id=123,
            scrape_date=date.today(),
            time_to_live=date.today(),
            skills={"Runecraft": 5_000_000, "Overall": 50_000_000},
            activities={
                "Abyssal Sire": 1200,
                "Barrows Chests": 5000,
                "Soul Wars Zeal": 9000,
                "LMS - Rank": 2500,
                "Chambers Of Xeric: Challenge Mode": 42,
                "Clue Scrolls (all)": 700,
            },
        ),
    )


def test_clean_dict_maps_jagex_names():
    cleaned = adapter.clean_dict({"Abyssal Sire": 1, "Runecraft": 2, "gone": None})

    assert cleaned == {"abyssal_sire": 1, "runecraft": 2}


def test_clean_dict_raises_on_non_dict():
    with pytest.raises(TypeError):
        adapter.clean_dict(["Abyssal Sire"])  # type: ignore[arg-type]


def test_transform_scraped_struct_keeps_activity_values(
    scraped_jagex_names: ScrapedStruct,
):
    data_to_predict = adapter.transform_scraped_struct(scraped_jagex_names)

    assert data_to_predict is not None
    hs = data_to_predict.data
    assert hs.abyssal_sire == 1200
    assert hs.barrows_chests == 5000
    assert hs.soul_wars_zeal == 9000
    assert hs.lms_rank == 2500
    assert hs.chambers_of_xeric_challenge_mode == 42
    assert hs.cs_all == 700
    assert hs.runecraft == 5_000_000


def test_transform_scraped_struct_returns_none_without_highscore(
    scraped_jagex_names: ScrapedStruct,
):
    record = scraped_jagex_names.model_copy(update={"highscore_data": None})

    assert adapter.transform_scraped_struct(record) is None
