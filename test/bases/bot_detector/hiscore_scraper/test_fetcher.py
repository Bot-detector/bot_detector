"""Unit tests for the fetch stage.

The fetch stage owns outcome branching (success, not_found, 407
rotation, transient errors) and per-proxy rate/retry state; Kafka side
effects belong to the processor and are not exercised here.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from aiohttp import RequestInfo
from bot_detector.event_queue.structs import ToScrapeStruct
from bot_detector.hiscore_scraper import fetcher
from bot_detector.hiscore_scraper.fetcher import ProxyRuntime, fetch
from bot_detector.hiscore_scraper.structs import FetchResult
from bot_detector.osrs_hs_api.exceptions import PlayerDoesNotExist
from bot_detector.structs import MetaData, PlayerStruct


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
