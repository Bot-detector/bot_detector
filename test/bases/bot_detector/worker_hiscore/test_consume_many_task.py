from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bot_detector.event_queue.structs import ScrapedStruct
from bot_detector.structs._metadata import MetaData
from bot_detector.structs.hiscore import HighscoreBaseStruct
from bot_detector.structs.player import PlayerStruct
from bot_detector.worker_hiscore.worker import HiscoreWorker, insert_batch


def _build_scraped_struct() -> ScrapedStruct:
    return ScrapedStruct(
        metadata=MetaData(version=1, source="test"),
        player_data=PlayerStruct(
            id=1,
            name="tester",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        ),
        highscore_data=HighscoreBaseStruct(
            player_id=1,
            scrape_date=date.today(),
            time_to_live=date.today(),
            skills={"attack": 99},
            activities={"league_points": 1},
        ),
    )


@pytest.mark.asyncio
async def test_insert_batch_calls_repos():
    batch = [_build_scraped_struct(), _build_scraped_struct()]
    session = AsyncMock()
    session.begin = MagicMock(return_value=AsyncMock())

    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    highscore_repo = AsyncMock()
    player_repo = AsyncMock()

    await insert_batch(
        session_factory=session_factory,
        batch=batch,
        highscore_repo=highscore_repo,
        player_repo=player_repo,
    )

    player_repo.update_many_players.assert_awaited_once()
    highscore_repo.insert_highscore_many.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_calls_insert_and_produces():
    batch = [_build_scraped_struct()]
    session_factory = MagicMock()
    highscore_repo = AsyncMock()
    player_repo = AsyncMock()
    data_to_predict_producer = AsyncMock()

    w = HiscoreWorker(
        worker_id=1,
        session_factory=session_factory,
        player_repo=player_repo,
        highscore_repo=highscore_repo,
        data_to_predict_producer=data_to_predict_producer,
    )

    with patch(
        "bot_detector.worker_hiscore.worker.insert_batch", new_callable=AsyncMock
    ) as mock_insert:
        await w.handle(batch)

    mock_insert.assert_awaited_once()
    data_to_predict_producer.put.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_skips_produce_when_highscore_is_none():
    scraped_no_hs = ScrapedStruct(
        metadata=MetaData(version=1, source="test"),
        player_data=PlayerStruct(
            id=1,
            name="tester",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        ),
        highscore_data=None,
    )
    batch = [scraped_no_hs]
    data_to_predict_producer = AsyncMock()

    w = HiscoreWorker(
        worker_id=1,
        session_factory=MagicMock(),
        player_repo=AsyncMock(),
        highscore_repo=AsyncMock(),
        data_to_predict_producer=data_to_predict_producer,
    )

    with patch(
        "bot_detector.worker_hiscore.worker.insert_batch", new_callable=AsyncMock
    ):
        await w.handle(batch)

    data_to_predict_producer.put.assert_awaited_once()
