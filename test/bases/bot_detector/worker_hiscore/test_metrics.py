from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from bot_detector.event_queue.structs import ScrapedStruct
from bot_detector.structs._metadata import MetaData
from bot_detector.structs.hiscore import HighscoreBaseStruct
from bot_detector.structs.player import PlayerStruct
from bot_detector.worker_hiscore.worker import HiscoreWorker, insert_batch
from prometheus_client import REGISTRY


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


def _sample(name: str) -> float | None:
    return REGISTRY.get_sample_value(name)


def _mock_session_factory() -> MagicMock:
    session = AsyncMock()
    session.begin = MagicMock(return_value=AsyncMock())
    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return session_factory


@pytest.mark.asyncio
async def test_insert_batch_increments_counters():
    batch = [_build_scraped_struct(), _build_scraped_struct()]
    players_before = _sample("highscore_worker_players_updated_total") or 0
    rows_before = _sample("highscore_worker_rows_inserted_total") or 0

    await insert_batch(
        session_factory=_mock_session_factory(),
        batch=batch,
        highscore_repo=AsyncMock(),
        player_repo=AsyncMock(),
    )

    assert (
        _sample("highscore_worker_players_updated_total") or 0
    ) == players_before + 2
    assert (_sample("highscore_worker_rows_inserted_total") or 0) == rows_before + 2


@pytest.mark.asyncio
async def test_handle_increments_to_predict_counter():
    batch = [_build_scraped_struct()]
    before = _sample("highscore_worker_to_predict_produced_total") or 0

    worker = HiscoreWorker(
        worker_id=0,
        session_factory=_mock_session_factory(),
        highscore_repo=AsyncMock(),
        player_repo=AsyncMock(),
        data_to_predict_producer=AsyncMock(),
    )
    await worker.handle(batch)

    assert (_sample("highscore_worker_to_predict_produced_total") or 0) == before + 1
