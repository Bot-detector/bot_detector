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
async def test_get_player_to_scrape_commits_message(monkeypatch: pytest.MonkeyPatch):
    player_ts_queue = AsyncMock()
    player_to_scrape = _to_scrape_player()
    player_ts_queue.get_one = AsyncMock(return_value=player_to_scrape)
    player_ts_queue.commit = AsyncMock(return_value=None)

    result = await core.get_player_to_scrape(
        worker_id=1, player_ts_queue=player_ts_queue
    )

    assert result == player_to_scrape
    player_ts_queue.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_work_requeues_player_when_publish_fails(monkeypatch: pytest.MonkeyPatch):
    _patch_common(monkeypatch)

    player_ts_queue = AsyncMock()
    player_sc_producer = AsyncMock()

    monkeypatch.setattr(
        core, "scrape_player", AsyncMock(return_value=(object(), False))
    )
    monkeypatch.setattr(
        core, "transform_player_stats", AsyncMock(return_value=_scraped_player())
    )
    produce_player_to_scrape = AsyncMock(return_value=None)
    monkeypatch.setattr(core, "produce_player_to_scrape", produce_player_to_scrape)
    monkeypatch.setattr(
        core,
        "produce_player_scraped",
        AsyncMock(return_value=Exception("publish failed")),
    )

    with pytest.raises(asyncio.CancelledError):
        await core.work(
            worker_id=1,
            proxy_manager=AsyncMock(),
            player_ts_queue=player_ts_queue,
            player_nf_producer=AsyncMock(),
            player_sc_producer=player_sc_producer,
        )

    produce_player_to_scrape.assert_awaited_once()
    requeued_player = produce_player_to_scrape.await_args.args[1]
    assert requeued_player.name == "player-1"
