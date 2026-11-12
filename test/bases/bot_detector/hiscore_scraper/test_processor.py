"""Unit tests for the processor stage.

The processor owns every Kafka side effect: not_found production,
transient-error requeue, transform + scraped production, and requeue
when publishing scraped data fails.
"""

import asyncio
import logging
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import ClientResponseError, RequestInfo
from bot_detector.event_queue.structs import ScrapedStruct
from bot_detector.hiscore_scraper import processor
from bot_detector.hiscore_scraper.structs import FetchResult
from bot_detector.osrs_hs_api.exceptions import PlayerDoesNotExist
from bot_detector.structs import HighscoreBaseStruct, MetaData, PlayerStruct
from multidict import CIMultiDict
from yarl import URL

PROCESSOR_LOGGER = "bot_detector.hiscore_scraper.processor"
URL_HS = "https://secure.runescape.com/m=hiscore_oldschool/index_lite.json"


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


def _gateway_error(player_name: str = "player-1") -> ClientResponseError:
    return ClientResponseError(
        request_info=RequestInfo(
            url=URL(f"{URL_HS}?player={player_name}"),
            method="GET",
            headers=CIMultiDict(),
        ),
        history=(),
        status=502,
        message="Bad Gateway",
        headers=CIMultiDict(
            {
                "Date": "Thu, 12 Nov 2026 13:26:20 GMT",
                "Content-Type": "text/html",
                "Server": "cloudflare",
                "Set-Cookie": "__cf_bm=cookie-value; HttpOnly; SameSite=None",
                "Strict-Transport-Security": "max-age=31536000;",
                "cf-cache-status": "DYNAMIC",
                "CF-RAY": "a595de2848fc8e6a-SJC",
            }
        ),
    )


def _wide_event_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [
        record
        for record in caplog.records
        if record.name == PROCESSOR_LOGGER and isinstance(record.msg, dict)
    ]


@pytest.mark.asyncio
async def test_transient_error_emits_warning_wide_event_with_json_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    player = _player(name="ladymicker")
    mocks = _patch_producers(monkeypatch, transform_return=None)
    results_queue = _enqueue(
        FetchResult(
            player=player, proxy="user@proxy-1:1080", error=_gateway_error("ladymicker")
        )
    )

    with caplog.at_level(logging.INFO, logger=PROCESSOR_LOGGER):
        task = await _process_one(results_queue)
        await asyncio.wait_for(
            _await_calls(mocks.produce_player_to_scrape), timeout=1.0
        )
        task.cancel()

    records = _wide_event_records(caplog)
    assert records, "expected a wide event log record"
    record = records[-1]
    assert record.levelno == logging.WARNING

    event = record.msg
    assert event["outcome"] == "error"
    assert event["processor"] == 0
    assert event["player"] == {"id": 1, "name": "ladymicker"}
    assert event["proxy"] == "proxy-1:1080"
    assert event["scrape_error"]["type"] == "ClientResponseError"
    assert event["scrape_error"]["status"] == 502
    assert event["scrape_error"]["message"] == "Bad Gateway"
    assert "player=ladymicker" in event["scrape_error"]["url"]
    assert event["scrape_error"]["headers"] == {
        "Date": "Thu, 12 Nov 2026 13:26:20 GMT",
        "Content-Type": "text/html",
        "Server": "cloudflare",
        "Strict-Transport-Security": "max-age=31536000;",
        "cf-cache-status": "DYNAMIC",
        "CF-RAY": "a595de2848fc8e6a-SJC",
    }
    assert "__cf_bm" not in record.getMessage()


@pytest.mark.asyncio
async def test_produce_failure_escalsates_to_error_level(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    player = _player()
    mocks = _patch_producers(monkeypatch, transform_return=None)
    mocks.produce_player_to_scrape = AsyncMock(return_value=Exception("kafka down"))
    monkeypatch.setattr(
        processor, "produce_player_to_scrape", mocks.produce_player_to_scrape
    )
    results_queue = _enqueue(
        FetchResult(player=player, proxy="user@proxy-1:1080", error=Exception("502"))
    )

    with caplog.at_level(logging.INFO, logger=PROCESSOR_LOGGER):
        task = await _process_one(results_queue)
        await asyncio.wait_for(
            _await_calls(mocks.produce_player_to_scrape), timeout=1.0
        )
        task.cancel()

    records = _wide_event_records(caplog)
    assert records, "expected a wide event log record"
    record = records[-1]
    assert record.levelno == logging.ERROR

    event = record.msg
    assert event["outcome"] == "error"
    assert event["scrape_error"]["message"] == "502"
    assert event["produce_errors"]["to_scrape"] == {
        "type": "Exception",
        "message": "kafka down",
    }


@pytest.mark.asyncio
async def test_not_found_emits_sampled_info_wide_event(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    monkeypatch.setattr(processor.wide_event, "sample_ratio", 1.0)
    player = _player()
    mocks = _patch_producers(monkeypatch, transform_return=None)
    results_queue = _enqueue(
        FetchResult(
            player=player,
            proxy="user@proxy-1:1080",
            error=PlayerDoesNotExist("Player 'player-1' does not exist."),
        )
    )

    with caplog.at_level(logging.INFO, logger=PROCESSOR_LOGGER):
        task = await _process_one(results_queue)
        await asyncio.wait_for(_await_calls(mocks.produce_not_found), timeout=1.0)
        task.cancel()

    records = _wide_event_records(caplog)
    assert records, "expected a wide event log record"
    record = records[-1]
    assert record.levelno == logging.INFO
    assert record.msg["outcome"] == "not_found"


@pytest.mark.asyncio
async def test_success_emits_sampled_info_wide_event(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    monkeypatch.setattr(processor.wide_event, "sample_ratio", 1.0)
    player = _player()
    mocks = _patch_producers(monkeypatch, transform_return=_scraped_struct(player))
    results_queue = _enqueue(
        FetchResult(player=player, proxy="user@proxy-1:1080", stats=object())
    )

    with caplog.at_level(logging.INFO, logger=PROCESSOR_LOGGER):
        task = await _process_one(results_queue)
        await asyncio.wait_for(_await_calls(mocks.produce_player_scraped), timeout=1.0)
        task.cancel()

    records = _wide_event_records(caplog)
    assert records, "expected a wide event log record"
    record = records[-1]
    assert record.levelno == logging.INFO
    assert record.msg["outcome"] == "success"


@pytest.mark.asyncio
async def test_wide_event_context_reset_between_results(
    monkeypatch: pytest.MonkeyPatch,
):
    """The per-result context must not leak into the next iteration."""
    monkeypatch.setattr(processor.wide_event, "sample_ratio", 1.0)
    mocks = _patch_producers(monkeypatch, transform_return=None)
    results_queue = _enqueue(
        FetchResult(
            player=_player(),
            proxy="user@proxy-1:1080",
            error=_gateway_error(),
        )
    )

    task = await _process_one(results_queue)
    await asyncio.wait_for(_await_calls(mocks.produce_player_to_scrape), timeout=1.0)
    task.cancel()

    assert processor.wide_event.get() == {}
