"""Unit tests for the processor stage.

The processor owns every Kafka side effect: not_found production,
transient-error requeue, transform + scraped production, and requeue
when publishing scraped data fails.
"""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from bot_detector.event_queue.structs import ScrapedStruct
from bot_detector.hiscore_scraper import processor
from bot_detector.hiscore_scraper.structs import FetchResult
from bot_detector.osrs_hs_api.exceptions import PlayerDoesNotExist
from bot_detector.structs import HighscoreBaseStruct, MetaData, PlayerStruct


def _player(player_id: int = 1, name: str = "player-1") -> PlayerStruct:
    return PlayerStruct(
        id=player_id,
        name=name,
        created_at=datetime(2024, 1, 1),
    )


def _scraped_struct(player: PlayerStruct) -> ScrapedStruct:
    return ScrapedStruct(
        metadata=MetaData(version=1, source="test"),
        player_data=player,
        highscore_data=HighscoreBaseStruct(
            player_id=player.id,
            scrape_date=datetime(2024, 1, 1).date(),
            skills={},
            activities={},
            time_to_live=datetime(2024, 1, 31).date(),
        ),
    )


def _patch_producers(
    monkeypatch: pytest.MonkeyPatch, transform_return: ScrapedStruct | None
) -> SimpleNamespace:
    """Patches transform + the three producer helpers onto the module."""
    mocks = SimpleNamespace(
        transform=AsyncMock(return_value=transform_return),
        produce_not_found=AsyncMock(return_value=None),
        produce_player_to_scrape=AsyncMock(return_value=None),
        produce_player_scraped=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(processor, "transform_player_stats", mocks.transform)
    monkeypatch.setattr(processor, "produce_not_found", mocks.produce_not_found)
    monkeypatch.setattr(
        processor, "produce_player_to_scrape", mocks.produce_player_to_scrape
    )
    monkeypatch.setattr(
        processor, "produce_player_scraped", mocks.produce_player_scraped
    )
    return mocks


def _enqueue(result: FetchResult) -> asyncio.Queue[FetchResult]:
    results_queue: asyncio.Queue[FetchResult] = asyncio.Queue(maxsize=10)
    results_queue.put_nowait(result)
    return results_queue


async def _process_one(results_queue: asyncio.Queue[FetchResult]) -> asyncio.Task:
    return asyncio.create_task(
        processor.process(
            processor_id=0,
            results_queue=results_queue,
            player_ts_queue=AsyncMock(),
            player_nf_producer=AsyncMock(),
            player_sc_producer=AsyncMock(),
        )
    )


async def _await_calls(mock: AsyncMock) -> None:
    """Waits until the mock has at least one awaited call."""
    while mock.await_count == 0:
        await asyncio.sleep(0.001)


@pytest.mark.asyncio
async def test_not_found_produces_not_found_struct(monkeypatch: pytest.MonkeyPatch):
    player = _player()
    mocks = _patch_producers(monkeypatch, transform_return=None)
    results_queue = _enqueue(
        FetchResult(
            player=player,
            proxy="user@proxy-1:1080",
            error=PlayerDoesNotExist("Player 'player-1' does not exist."),
        )
    )

    task = await _process_one(results_queue)
    await asyncio.wait_for(_await_calls(mocks.produce_not_found), timeout=1.0)
    task.cancel()

    mocks.produce_not_found.assert_awaited_once()
    requeued_player = mocks.produce_not_found.await_args.args[1]
    assert requeued_player.possible_ban is True
    mocks.produce_player_to_scrape.assert_not_awaited()


@pytest.mark.asyncio
async def test_transient_error_requeues_to_kafka(monkeypatch: pytest.MonkeyPatch):
    player = _player()
    mocks = _patch_producers(monkeypatch, transform_return=None)
    results_queue = _enqueue(
        FetchResult(player=player, proxy="user@proxy-1:1080", error=Exception("502"))
    )

    task = await _process_one(results_queue)
    await asyncio.wait_for(_await_calls(mocks.produce_player_to_scrape), timeout=1.0)
    task.cancel()

    mocks.produce_player_to_scrape.assert_awaited_once()
    requeued_player = mocks.produce_player_to_scrape.await_args.args[1]
    assert requeued_player.id == 1
    mocks.produce_not_found.assert_not_awaited()


@pytest.mark.asyncio
async def test_success_transforms_and_produces_scraped(
    monkeypatch: pytest.MonkeyPatch,
):
    player = _player()
    scraped = _scraped_struct(player)
    mocks = _patch_producers(monkeypatch, transform_return=scraped)
    results_queue = _enqueue(
        FetchResult(player=player, proxy="user@proxy-1:1080", stats=object())
    )

    task = await _process_one(results_queue)
    await asyncio.wait_for(_await_calls(mocks.produce_player_scraped), timeout=1.0)
    task.cancel()

    mocks.transform.assert_awaited_once()
    mocks.produce_player_scraped.assert_awaited_once()
    produced = mocks.produce_player_scraped.await_args.args[1]
    assert produced is scraped


@pytest.mark.asyncio
async def test_publish_failure_requeues_player(monkeypatch: pytest.MonkeyPatch):
    player = _player()
    scraped = _scraped_struct(player)
    mocks = _patch_producers(monkeypatch, transform_return=scraped)
    mocks.produce_player_scraped = AsyncMock(return_value=Exception("publish failed"))
    monkeypatch.setattr(
        processor, "produce_player_scraped", mocks.produce_player_scraped
    )
    results_queue = _enqueue(
        FetchResult(player=player, proxy="user@proxy-1:1080", stats=object())
    )

    task = await _process_one(results_queue)
    await asyncio.wait_for(_await_calls(mocks.produce_player_to_scrape), timeout=1.0)
    task.cancel()

    mocks.produce_player_scraped.assert_awaited_once()
    mocks.produce_player_to_scrape.assert_awaited_once()
    requeued_player = mocks.produce_player_to_scrape.await_args.args[1]
    assert requeued_player.id == 1


@pytest.mark.asyncio
async def test_transform_none_skips_scraped_production(
    monkeypatch: pytest.MonkeyPatch,
):
    player = _player()
    mocks = _patch_producers(monkeypatch, transform_return=None)
    results_queue = _enqueue(
        FetchResult(player=player, proxy="user@proxy-1:1080", stats=object())
    )

    task = await _process_one(results_queue)
    await asyncio.wait_for(_await_calls(mocks.transform), timeout=1.0)
    task.cancel()

    # transform already requeued the player internally; the processor
    # must not also publish a scraped struct
    mocks.produce_player_scraped.assert_not_awaited()
    mocks.produce_player_to_scrape.assert_not_awaited()
