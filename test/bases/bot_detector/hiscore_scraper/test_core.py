import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from bot_detector.event_queue.structs import ScrapedStruct, ToScrapeStruct
from bot_detector.hiscore_scraper import core
from bot_detector.structs import HighscoreBaseStruct, MetaData, PlayerStruct


class _DummySession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _to_scrape_player() -> ToScrapeStruct:
    player = PlayerStruct(
        id=1,
        name="player-1",
        created_at=datetime(2024, 1, 1),
    )
    return ToScrapeStruct(
        metadata=MetaData(version=1, source="test"),
        player_data=player,
    )


def _scraped_player() -> ScrapedStruct:
    player = PlayerStruct(
        id=1,
        name="player-1",
        created_at=datetime(2024, 1, 1),
    )
    return ScrapedStruct(
        metadata=MetaData(version=1, source="test"),
        player_data=player,
        highscore_data=HighscoreBaseStruct(
            player_id=1,
            scrape_date=datetime(2024, 1, 1).date(),
            skills={},
            activities={},
            time_to_live=datetime(2024, 1, 31).date(),
        ),
    )


def _patch_common(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(core, "ClientSession", lambda *args, **kwargs: _DummySession())
    monkeypatch.setattr(core, "RateLimiter", lambda *args, **kwargs: object())
    monkeypatch.setattr(core, "Hiscore", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        core,
        "ProxySettings",
        lambda: SimpleNamespace(MAX_CALLS=100, INTERVAL=60),
    )
    monkeypatch.setattr(
        core,
        "get_proxy",
        AsyncMock(side_effect=["user@proxy", asyncio.CancelledError()]),
    )
    monkeypatch.setattr(
        core, "get_player_to_scrape", AsyncMock(return_value=_to_scrape_player())
    )


@pytest.mark.asyncio
async def test_work_commits_after_successful_publish(monkeypatch: pytest.MonkeyPatch):
    _patch_common(monkeypatch)

    player_ts_queue = AsyncMock()
    player_ts_queue.commit = AsyncMock(return_value=None)

    player_sc_producer = AsyncMock()
    player_sc_producer.put = AsyncMock(return_value=None)

    monkeypatch.setattr(
        core, "scrape_player", AsyncMock(return_value=(object(), False))
    )
    monkeypatch.setattr(
        core, "transform_player_stats", AsyncMock(return_value=_scraped_player())
    )

    with pytest.raises(asyncio.CancelledError):
        await core.work(
            worker_id=1,
            proxy_manager=AsyncMock(),
            player_ts_queue=player_ts_queue,
            player_nf_producer=AsyncMock(),
            player_sc_producer=player_sc_producer,
        )

    player_ts_queue.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_work_does_not_commit_on_retry(monkeypatch: pytest.MonkeyPatch):
    _patch_common(monkeypatch)

    player_ts_queue = AsyncMock()
    player_ts_queue.commit = AsyncMock(return_value=None)

    monkeypatch.setattr(core, "scrape_player", AsyncMock(return_value=(None, True)))
    monkeypatch.setattr(core, "handle_retry", AsyncMock())

    with pytest.raises(asyncio.CancelledError):
        await core.work(
            worker_id=1,
            proxy_manager=AsyncMock(),
            player_ts_queue=player_ts_queue,
            player_nf_producer=AsyncMock(),
            player_sc_producer=AsyncMock(),
        )

    player_ts_queue.commit.assert_not_awaited()
