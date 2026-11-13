"""Unit tests for the fetch stage.

The fetch stage owns outcome branching (success, not_found, 407
rotation, transient errors) and per-proxy rate/retry state; Kafka side
effects belong to the processor and are not exercised here.
"""

import asyncio
import logging
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from aiohttp import ClientResponseError, RequestInfo
from bot_detector.event_queue.structs import ToScrapeStruct
from bot_detector.hiscore_scraper.flow import fetcher
from bot_detector.hiscore_scraper.flow.fetcher import fetch
from bot_detector.hiscore_scraper.flow.structs import FetchResult
from bot_detector.hiscore_scraper.proxy_pool.runtime import ProxyRuntime
from bot_detector.osrs_hs_api.exceptions import PlayerDoesNotExist
from bot_detector.structs import MetaData, PlayerStruct
from multidict import CIMultiDict
from yarl import URL

FETCHER_LOGGER = "bot_detector.hiscore_scraper.flow.fetcher"
URL_HS = "https://secure.runescape.com/m=hiscore_oldschool/index_lite.json"


@pytest.fixture(autouse=True)
def _proxy_env(monkeypatch: pytest.MonkeyPatch):
    # ProxyRuntime reads ProxySettings, which requires an API key
    monkeypatch.setenv("PROXY_API_KEY", "test")


class _FakeProxyManager:
    def __init__(self, proxies: list[str] | None) -> None:
        self._proxies = proxies
        self.rotations = 0

    async def get_proxy(self, index=None):
        if self._proxies is None:
            return None, Exception("no proxies")
        return list(self._proxies), None

    async def rotate_proxies(self):
        self.rotations += 1


def _to_scrape_player(player_id: int = 1) -> ToScrapeStruct:
    player = PlayerStruct(
        id=player_id,
        name=f"player-{player_id}",
        created_at=datetime(2024, 1, 1),
    )
    return ToScrapeStruct(
        metadata=MetaData(version=1, source="test"),
        player_data=player,
    )


def _runtime(monkeypatch: pytest.MonkeyPatch, proxies: list[str] | None):
    """ProxyRuntime over a fake manager with sleeps patched out."""
    manager = _FakeProxyManager(proxies)
    runtime = ProxyRuntime(proxy_manager=manager)  # type: ignore[arg-type]
    monkeypatch.setattr(fetcher, "ROTATE_COOLDOWN_S", 0.0)
    monkeypatch.setattr(fetcher, "NO_PROXY_SLEEP_S", 0.0)
    monkeypatch.setattr(fetcher, "record_failure", MagicMock(return_value=0.0))
    return runtime, manager


async def _first_result(results_queue: asyncio.Queue[FetchResult]):
    return await asyncio.wait_for(results_queue.get(), timeout=1.0)


@pytest.mark.asyncio
async def test_fetch_success_pushes_result_with_stats(
    monkeypatch: pytest.MonkeyPatch,
):
    stats = object()
    monkeypatch.setattr(fetcher, "scrape_player", AsyncMock(return_value=(stats, None)))
    runtime, _manager = _runtime(monkeypatch, ["user@proxy-1:1080"])
    task_queue: asyncio.Queue[ToScrapeStruct] = asyncio.Queue(maxsize=10)
    task_queue.put_nowait(_to_scrape_player())
    results_queue: asyncio.Queue[FetchResult] = asyncio.Queue(maxsize=10)

    task = asyncio.create_task(
        fetch(
            fetcher_id=0,
            runtime=runtime,
            task_queue=task_queue,
            results_queue=results_queue,
            session=AsyncMock(),
        )
    )
    result = await _first_result(results_queue)
    task.cancel()

    assert result.stats is stats
    assert result.error is None
    assert result.proxy == "user@proxy-1:1080"
    assert result.player.id == 1


@pytest.mark.asyncio
async def test_fetch_not_found_pushes_error_without_backoff(
    monkeypatch: pytest.MonkeyPatch,
):
    error = PlayerDoesNotExist("Player 'x' does not exist.")
    monkeypatch.setattr(fetcher, "scrape_player", AsyncMock(return_value=(None, error)))
    runtime, _manager = _runtime(monkeypatch, ["user@proxy-1:1080"])
    task_queue: asyncio.Queue[ToScrapeStruct] = asyncio.Queue(maxsize=10)
    task_queue.put_nowait(_to_scrape_player())
    results_queue: asyncio.Queue[FetchResult] = asyncio.Queue(maxsize=10)

    task = asyncio.create_task(
        fetch(
            fetcher_id=0,
            runtime=runtime,
            task_queue=task_queue,
            results_queue=results_queue,
            session=AsyncMock(),
        )
    )
    result = await _first_result(results_queue)
    task.cancel()

    assert result.error is error
    # not_found is an outcome, not a failure: no retry tracking
    fetcher.record_failure.assert_not_called()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_fetch_rotates_proxies_on_407(monkeypatch: pytest.MonkeyPatch):
    proxy_error = aiohttp.ClientHttpProxyError(
        request_info=RequestInfo(
            url="http://example.com",
            method="GET",
            headers={},
        ),
        history=(),
        status=407,
        message="Proxy Authentication Required",
    )
    monkeypatch.setattr(
        fetcher, "scrape_player", AsyncMock(return_value=(None, proxy_error))
    )
    runtime, manager = _runtime(monkeypatch, ["user@proxy-1:1080"])
    task_queue: asyncio.Queue[ToScrapeStruct] = asyncio.Queue(maxsize=10)
    task_queue.put_nowait(_to_scrape_player())
    results_queue: asyncio.Queue[FetchResult] = asyncio.Queue(maxsize=10)

    task = asyncio.create_task(
        fetch(
            fetcher_id=0,
            runtime=runtime,
            task_queue=task_queue,
            results_queue=results_queue,
            session=AsyncMock(),
        )
    )
    result = await _first_result(results_queue)
    task.cancel()

    assert manager.rotations == 1
    assert result.error is proxy_error
    # proxy errors do hit the retry tracker
    fetcher.record_failure.assert_called_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_fetch_requeues_task_when_no_proxies(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        fetcher, "scrape_player", AsyncMock(return_value=(None, Exception("unused")))
    )
    runtime, _manager = _runtime(monkeypatch, None)
    player = _to_scrape_player()
    task_queue: asyncio.Queue[ToScrapeStruct] = asyncio.Queue(maxsize=10)
    task_queue.put_nowait(player)
    results_queue: asyncio.Queue[FetchResult] = asyncio.Queue(maxsize=10)

    task = asyncio.create_task(
        fetch(
            fetcher_id=0,
            runtime=runtime,
            task_queue=task_queue,
            results_queue=results_queue,
            session=AsyncMock(),
        )
    )
    # the player goes back into the task queue instead of being dropped
    requeued = await asyncio.wait_for(task_queue.get(), timeout=1.0)
    task.cancel()

    assert requeued is player
    assert results_queue.empty()


@pytest.mark.asyncio
async def test_proxy_runtime_shares_state_per_proxy():
    runtime = ProxyRuntime(proxy_manager=AsyncMock())  # type: ignore[arg-type]
    limiter_a1 = runtime.limiter("user@proxy-a:1")
    limiter_a2 = runtime.limiter("user@proxy-a:1")
    limiter_b = runtime.limiter("user@proxy-b:1")

    assert limiter_a1 is limiter_a2
    assert limiter_a1 is not limiter_b

    tracker_a1, id_a1 = runtime.tracker("user@proxy-a:1")
    tracker_a2, id_a2 = runtime.tracker("user@proxy-a:1")
    tracker_b, id_b = runtime.tracker("user@proxy-b:1")

    assert tracker_a1 is tracker_a2 and id_a1 == id_a2
    assert tracker_a1 is not tracker_b and id_a1 != id_b

    assert runtime.api("user@proxy-a:1") is runtime.api("user@proxy-a:1")


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
                "cf-cache-status": "DYNAMIC",
                "CF-RAY": "a595de2848fc8e6a-SJC",
            }
        ),
    )


def _wide_event_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [
        record
        for record in caplog.records
        if record.name == FETCHER_LOGGER and isinstance(record.msg, dict)
    ]


async def _wait_for_event(caplog: pytest.LogCaptureFixture, timeout: float = 1.0):
    """Waits until the fetcher has emitted its wide event for this attempt.

    The event is emitted in the loop's finally, which can lag the
    results_queue put (e.g. during the backoff sleep).
    """

    async def poll():
        while not _wide_event_records(caplog):
            await asyncio.sleep(0.001)

    await asyncio.wait_for(poll(), timeout=timeout)


def _fetch_one(
    monkeypatch: pytest.MonkeyPatch,
    runtime: ProxyRuntime,
    scrape_return: tuple[object, Exception | None],
) -> asyncio.Queue[FetchResult]:
    """Starts fetch() with one queued player and scrape_player patched."""
    monkeypatch.setattr(fetcher, "scrape_player", AsyncMock(return_value=scrape_return))
    task_queue: asyncio.Queue[ToScrapeStruct] = asyncio.Queue(maxsize=10)
    task_queue.put_nowait(_to_scrape_player())
    results_queue: asyncio.Queue[FetchResult] = asyncio.Queue(maxsize=10)
    asyncio.create_task(
        fetch(
            fetcher_id=0,
            runtime=runtime,
            task_queue=task_queue,
            results_queue=results_queue,
            session=AsyncMock(),
        )
    )
    return results_queue


def _cancel_fetchers() -> None:
    """Cancels the fetch task(s) started by a test, not the test itself."""
    for task in asyncio.all_tasks() - {asyncio.current_task()}:
        task.cancel()


@pytest.mark.asyncio
async def test_fetch_success_emits_sampled_info_wide_event(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    monkeypatch.setattr(fetcher.wide_event, "sample_ratio", 1.0)
    runtime, _manager = _runtime(monkeypatch, ["user@proxy-1:1080"])
    results_queue = _fetch_one(monkeypatch, runtime, (object(), None))

    with caplog.at_level(logging.INFO, logger=FETCHER_LOGGER):
        await _first_result(results_queue)

    _cancel_fetchers()

    records = _wide_event_records(caplog)
    assert records, "expected a wide event log record"
    record = records[-1]
    assert record.levelno == logging.INFO
    assert record.msg == {
        "fetcher": 0,
        "player": {"id": 1, "name": "player-1"},
        "proxy": "proxy-1:1080",
        "outcome": "success",
        "log_reason": "sample",
    }


@pytest.mark.asyncio
async def test_fetch_transient_error_emits_warning_wide_event(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    runtime, _manager = _runtime(monkeypatch, ["user@proxy-1:1080"])
    monkeypatch.setattr(fetcher, "record_failure", MagicMock(return_value=1.5))
    results_queue = _fetch_one(
        monkeypatch, runtime, (None, _gateway_error("ladymicker"))
    )

    with caplog.at_level(logging.INFO, logger=FETCHER_LOGGER):
        await _first_result(results_queue)
        # emit happens in the finally, after the full backoff sleep
        await _wait_for_event(caplog, timeout=3.0)
        _cancel_fetchers()

    records = _wide_event_records(caplog)
    assert records, "expected a wide event log record"
    record = records[-1]
    assert record.levelno == logging.WARNING

    event = record.msg
    assert event["fetcher"] == 0
    assert event["proxy"] == "proxy-1:1080"
    assert event["outcome"] == "error"
    assert event["backoff_seconds"] == 1.5
    assert event["scrape_error"]["status"] == 502
    assert event["scrape_error"]["headers"]["CF-RAY"] == "a595de2848fc8e6a-SJC"
    assert "__cf_bm" not in record.getMessage()


@pytest.mark.asyncio
async def test_fetch_407_emits_warning_with_proxy_rotated(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    proxy_error = aiohttp.ClientHttpProxyError(
        request_info=RequestInfo(
            url="http://proxy-1:1080",
            method="GET",
            headers={},
        ),
        history=(),
        status=407,
        message="Proxy Authentication Required",
    )
    runtime, manager = _runtime(monkeypatch, ["user@proxy-1:1080"])
    results_queue = _fetch_one(monkeypatch, runtime, (None, proxy_error))

    with caplog.at_level(logging.INFO, logger=FETCHER_LOGGER):
        await _first_result(results_queue)
        await _wait_for_event(caplog)
        _cancel_fetchers()

    records = _wide_event_records(caplog)
    assert records, "expected a wide event log record"
    event = records[-1].msg
    assert records[-1].levelno == logging.WARNING
    assert event["outcome"] == "error"
    assert event["proxy_rotated"] is True
    assert manager.rotations == 1


@pytest.mark.asyncio
async def test_fetch_not_found_emits_info_wide_event(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    monkeypatch.setattr(fetcher.wide_event, "sample_ratio", 1.0)
    error = PlayerDoesNotExist("Player 'player-1' does not exist.")
    runtime, _manager = _runtime(monkeypatch, ["user@proxy-1:1080"])
    results_queue = _fetch_one(monkeypatch, runtime, (None, error))

    with caplog.at_level(logging.INFO, logger=FETCHER_LOGGER):
        await _first_result(results_queue)
        await asyncio.sleep(0.05)

    _cancel_fetchers()

    records = _wide_event_records(caplog)
    assert records, "expected a wide event log record"
    assert records[-1].levelno == logging.INFO
    assert records[-1].msg["outcome"] == "not_found"


@pytest.mark.asyncio
async def test_fetch_no_proxies_emits_error_wide_event(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    runtime, _manager = _runtime(monkeypatch, None)
    task_queue: asyncio.Queue[ToScrapeStruct] = asyncio.Queue(maxsize=10)
    player = _to_scrape_player()
    task_queue.put_nowait(player)
    results_queue: asyncio.Queue[FetchResult] = asyncio.Queue(maxsize=10)

    with caplog.at_level(logging.INFO, logger=FETCHER_LOGGER):
        task = asyncio.create_task(
            fetch(
                fetcher_id=0,
                runtime=runtime,
                task_queue=task_queue,
                results_queue=results_queue,
                session=AsyncMock(),
            )
        )
        # the fetcher must run first: awaiting the non-empty task_queue
        # here would starve it before its first step
        await _wait_for_event(caplog)
        requeued = await asyncio.wait_for(task_queue.get(), timeout=1.0)
        task.cancel()

    assert requeued is player
    records = _wide_event_records(caplog)
    assert records, "expected a wide event log record"
    assert records[-1].levelno == logging.ERROR
    assert records[-1].msg["outcome"] == "no_proxies"


@pytest.mark.asyncio
async def test_fetch_wide_event_context_reset_between_players(
    monkeypatch: pytest.MonkeyPatch,
):
    runtime, _manager = _runtime(monkeypatch, ["user@proxy-1:1080"])
    results_queue = _fetch_one(monkeypatch, runtime, (None, _gateway_error()))

    await _first_result(results_queue)
    await asyncio.sleep(0.05)
    _cancel_fetchers()

    assert fetcher.wide_event.get() == {}
