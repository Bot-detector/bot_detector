from datetime import date, datetime
from unittest.mock import AsyncMock

import pytest

from bot_detector.event_queue.structs import ScrapedStruct
from bot_detector.structs._metadata import MetaData
from bot_detector.structs.hiscore import HighscoreBaseStruct
from bot_detector.structs.player import PlayerStruct
from bot_detector.worker_hiscore import core


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
async def test_hiscore_worker_raises_on_insert_error(
    monkeypatch: pytest.MonkeyPatch,
):
    batch = [_build_scraped_struct(), _build_scraped_struct()]

    async def _fake_insert_batch(**_kwargs):
        return None, "insert-failed"

    monkeypatch.setattr(core, "insert_batch", _fake_insert_batch)

    worker = core.HiscoreWorker(
        worker_id=1,
        session_factory=AsyncMock(),
        highscore_repo=AsyncMock(),
        player_repo=AsyncMock(),
        data_to_predict_producer=AsyncMock(),
    )

    with pytest.raises(RuntimeError, match="insert-failed"):
        await worker.handle(batch)


@pytest.mark.asyncio
async def test_hiscore_worker_succeeds_on_valid_batch(
    monkeypatch: pytest.MonkeyPatch,
):
    batch = [_build_scraped_struct(), _build_scraped_struct()]

    async def _fake_insert_batch(**_kwargs):
        return None, None

    monkeypatch.setattr(core, "insert_batch", _fake_insert_batch)

    data_to_predict_producer = AsyncMock()

    worker = core.HiscoreWorker(
        worker_id=1,
        session_factory=AsyncMock(),
        highscore_repo=AsyncMock(),
        player_repo=AsyncMock(),
        data_to_predict_producer=data_to_predict_producer,
    )

    await worker.handle(batch)


@pytest.mark.asyncio
async def test_hiscore_worker_produces_to_predict_topic(
    monkeypatch: pytest.MonkeyPatch,
):
    batch = [_build_scraped_struct()]

    async def _fake_insert_batch(**_kwargs):
        return None, None

    monkeypatch.setattr(core, "insert_batch", _fake_insert_batch)

    data_to_predict_producer = AsyncMock()

    worker = core.HiscoreWorker(
        worker_id=1,
        session_factory=AsyncMock(),
        highscore_repo=AsyncMock(),
        player_repo=AsyncMock(),
        data_to_predict_producer=data_to_predict_producer,
    )

    await worker.handle(batch)

    data_to_predict_producer.put.assert_awaited()
