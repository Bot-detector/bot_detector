from datetime import datetime
from unittest.mock import AsyncMock

import aiohttp
import pytest
from aiohttp import RequestInfo
from bot_detector.hiscore_scraper.scraping import service as scrape
from bot_detector.structs import PlayerStruct


@pytest.mark.asyncio
async def test_scrape_player_with_proxy():
    from bot_detector.osrs_hs_api.exceptions import Ok
    from bot_detector.osrs_hs_api.structs import Activity, PlayerStats, Skill

    api = AsyncMock()
    player = PlayerStruct(id=1, name="test_player", created_at=datetime(2024, 1, 1))
    session = AsyncMock()
    proxy = "http://user:pass@proxy.example.com:8080"

    player_stats = PlayerStats(
        skills=[Skill(id=0, name="Attack", rank=1000, level=99, xp=13034431)],
        activities=[Activity(id=0, name="Bounty Hunter", rank=500, score=100)],
    )
    api.get.return_value = Ok(value=player_stats, latency=0.5)

    result_stats, result_error = await scrape.scrape_player(
        player=player,
        session=session,
        api=api,
        proxy=proxy,
    )

    api.get.assert_awaited_once_with(player="test_player", session=session, proxy=proxy)
    assert result_stats is not None
    assert result_error is None


@pytest.mark.asyncio
async def test_scrape_player_returns_err_not_found():
    from bot_detector.osrs_hs_api.exceptions import Err, PlayerDoesNotExist

    api = AsyncMock()
    player = PlayerStruct(id=1, name="nonexistent", created_at=datetime(2024, 1, 1))
    session = AsyncMock()
    proxy = "http://user:pass@proxy.example.com:8080"

    api.get.return_value = Err(error=PlayerDoesNotExist("Player not found"))

    result_stats, result_error = await scrape.scrape_player(
        player=player,
        session=session,
        api=api,
        proxy=proxy,
    )

    assert result_stats is None
    assert isinstance(result_error, PlayerDoesNotExist)


@pytest.mark.asyncio
async def test_scrape_player_returns_err_proxy_error():
    from bot_detector.osrs_hs_api.exceptions import Err

    api = AsyncMock()
    player = PlayerStruct(id=1, name="test_player", created_at=datetime(2024, 1, 1))
    session = AsyncMock()
    proxy = "http://user:pass@proxy.example.com:8080"

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
    api.get.return_value = Err(error=proxy_error)

    result_stats, result_error = await scrape.scrape_player(
        player=player,
        session=session,
        api=api,
        proxy=proxy,
    )

    assert result_stats is None
    assert isinstance(result_error, aiohttp.ClientHttpProxyError)
    assert result_error.status == 407


def _outcome_count(proxy: str, outcome: str) -> float | None:
    from prometheus_client import REGISTRY

    return REGISTRY.get_sample_value(
        "hiscore_scraper_fetch_outcome_latency_seconds_count",
        labels={"proxy": proxy, "outcome": outcome},
    )


PROXY_LABEL = "proxy.example.com:8080"


@pytest.mark.asyncio
async def test_scrape_player_observes_success_latency():
    from bot_detector.osrs_hs_api.exceptions import Ok

    api = AsyncMock()
    player = PlayerStruct(id=1, name="p", created_at=datetime(2024, 1, 1))
    api.get.return_value = Ok(value=object(), latency=0.5)

    before = _outcome_count(PROXY_LABEL, "success") or 0.0
    await scrape.scrape_player(
        player=player, session=AsyncMock(), api=api, proxy="user@proxy.example.com:8080"
    )

    after = _outcome_count(PROXY_LABEL, "success")
    assert after is not None
    assert after == before + 1


@pytest.mark.asyncio
async def test_scrape_player_observes_not_found_latency():
    from bot_detector.osrs_hs_api.exceptions import Err, PlayerDoesNotExist

    api = AsyncMock()
    player = PlayerStruct(id=1, name="p", created_at=datetime(2024, 1, 1))
    api.get.return_value = Err(error=PlayerDoesNotExist("does not exist"), latency=2.5)

    before_nf = _outcome_count(PROXY_LABEL, "not_found") or 0.0
    before_ok = _outcome_count(PROXY_LABEL, "success") or 0.0
    stats, error = await scrape.scrape_player(
        player=player, session=AsyncMock(), api=api, proxy="user@proxy.example.com:8080"
    )

    assert stats is None
    assert isinstance(error, PlayerDoesNotExist)
    after_nf = _outcome_count(PROXY_LABEL, "not_found")
    assert after_nf is not None
    assert after_nf == before_nf + 1
    assert (_outcome_count(PROXY_LABEL, "success") or 0.0) == before_ok


@pytest.mark.asyncio
async def test_scrape_player_observes_error_latency():
    from bot_detector.osrs_hs_api.exceptions import Err

    api = AsyncMock()
    player = PlayerStruct(id=1, name="p", created_at=datetime(2024, 1, 1))
    api.get.return_value = Err(error=RuntimeError("boom"), latency=1.2)

    before = _outcome_count(PROXY_LABEL, "error") or 0.0
    await scrape.scrape_player(
        player=player, session=AsyncMock(), api=api, proxy="user@proxy.example.com:8080"
    )

    after = _outcome_count(PROXY_LABEL, "error")
    assert after is not None
    assert after == before + 1


@pytest.mark.asyncio
async def test_scrape_player_skips_zero_latency_err():
    # legacy mocked Err without a fetch: nothing to observe
    from bot_detector.osrs_hs_api.exceptions import Err, PlayerDoesNotExist

    api = AsyncMock()
    player = PlayerStruct(id=1, name="p", created_at=datetime(2024, 1, 1))
    api.get.return_value = Err(error=PlayerDoesNotExist("does not exist"))

    before_nf = _outcome_count(PROXY_LABEL, "not_found") or 0.0
    before_err = _outcome_count(PROXY_LABEL, "error") or 0.0
    await scrape.scrape_player(
        player=player, session=AsyncMock(), api=api, proxy="user@proxy.example.com:8080"
    )

    assert (_outcome_count(PROXY_LABEL, "not_found") or 0.0) == before_nf
    assert (_outcome_count(PROXY_LABEL, "error") or 0.0) == before_err
