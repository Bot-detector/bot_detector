import re
from unittest.mock import AsyncMock

import pytest
from aiohttp import ClientError, ClientSession
from aioresponses import aioresponses
from bot_detector.osrs_hs_api.core import HiscoreOldSchoolAPI
from bot_detector.osrs_hs_api.exceptions import (
    PlayerDoesNotExist,
    UnexpectedRedirection,
)


def _valid_hiscore_payload():
    return {
        "skills": [
            {"id": 0, "name": "Attack", "rank": 1000, "level": 99, "xp": 13034431}
        ],
        "activities": [{"id": 0, "name": "Bounty Hunter", "rank": 500, "score": 100}],
    }


URL_PATTERN = re.compile(
    r"^https://secure\.runescape\.com/m=hiscore_oldschool/index_lite\.json.*$"
)


@pytest.mark.asyncio
async def test_get_success():
    api = HiscoreOldSchoolAPI()

    with aioresponses() as m:
        m.get(URL_PATTERN, payload=_valid_hiscore_payload(), status=200)

        async with ClientSession() as session:
            result = await api.get("zezima", session)

    assert result.is_ok()
    assert result.value.skills[0].name == "Attack"
    assert result.latency > 0


@pytest.mark.asyncio
async def test_get_player_not_found():
    api = HiscoreOldSchoolAPI()

    with aioresponses() as m:
        m.get(URL_PATTERN, status=404)

        async with ClientSession() as session:
            result = await api.get("nonexistent_player", session)

    assert result.is_err()
    assert isinstance(result.error, PlayerDoesNotExist)


@pytest.mark.asyncio
async def test_get_unexpected_redirect():
    api = HiscoreOldSchoolAPI()

    with aioresponses() as m:
        m.get(
            URL_PATTERN,
            status=302,
            headers={"Location": "https://runescape.com/"},
        )
        m.get("https://runescape.com/", status=200, payload={})

        async with ClientSession() as session:
            result = await api.get("player", session)

    assert result.is_err()
    assert isinstance(result.error, UnexpectedRedirection)


@pytest.mark.asyncio
async def test_get_server_error():
    api = HiscoreOldSchoolAPI()

    with aioresponses() as m:
        m.get(URL_PATTERN, status=500)

        async with ClientSession() as session:
            result = await api.get("player", session)

    assert result.is_err()
    assert isinstance(result.error, Exception)


@pytest.mark.asyncio
async def test_get_connection_error():
    api = HiscoreOldSchoolAPI()

    with aioresponses() as m:
        m.get(URL_PATTERN, exception=ClientError("connection failed"))

        async with ClientSession() as session:
            result = await api.get("player", session)

    assert result.is_err()
    assert isinstance(result.error, ClientError)


@pytest.mark.asyncio
async def test_transform_invalid_data():
    from pydantic import ValidationError

    api = HiscoreOldSchoolAPI()

    with aioresponses() as m:
        m.get(URL_PATTERN, payload={"invalid": "structure"}, status=200)

        async with ClientSession() as session:
            result = await api.get("player", session)

    assert result.is_err()
    assert isinstance(result.error, ValidationError)


@pytest.mark.asyncio
async def test_rate_limiter_is_called():
    mock_limiter = AsyncMock()
    api = HiscoreOldSchoolAPI(rate_limiter=mock_limiter)

    with aioresponses() as m:
        m.get(URL_PATTERN, payload=_valid_hiscore_payload(), status=200)

        async with ClientSession() as session:
            await api.get("player", session)

    mock_limiter.check.assert_awaited_once()


@pytest.mark.asyncio
async def test_latency_is_recorded():
    api = HiscoreOldSchoolAPI()

    with aioresponses() as m:
        m.get(URL_PATTERN, payload=_valid_hiscore_payload(), status=200)

        async with ClientSession() as session:
            result = await api.get("zezima", session)

    assert result.is_ok()
    assert isinstance(result.latency, float)
    assert result.latency >= 0


@pytest.mark.asyncio
async def test_get_with_proxy_passes_to_session():
    from unittest.mock import patch

    api = HiscoreOldSchoolAPI()
    proxy_url = "http://user:pass@proxy.example.com:8080"

    with aioresponses() as m:
        m.get(URL_PATTERN, payload=_valid_hiscore_payload(), status=200)

        async with ClientSession() as session:
            with patch.object(session, "get", wraps=session.get) as mock_get:
                result = await api.get("zezima", session, proxy=proxy_url)

                mock_get.assert_called_once()
                call_kwargs = mock_get.call_args[1]
                assert call_kwargs.get("proxy") == proxy_url

    assert result.is_ok()


@pytest.mark.asyncio
async def test_get_with_proxy_error():
    from aiohttp import ClientHttpProxyError, RequestInfo

    api = HiscoreOldSchoolAPI()
    proxy_url = "http://user:pass@proxy.example.com:8080"

    with aioresponses() as m:
        m.get(
            URL_PATTERN,
            exception=ClientHttpProxyError(
                request_info=RequestInfo(
                    url="http://example.com",
                    method="GET",
                    headers={},
                ),
                history=(),
                status=407,
                message="Proxy Authentication Required",
            ),
        )

        async with ClientSession() as session:
            result = await api.get("player", session, proxy=proxy_url)

    assert result.is_err()
    assert isinstance(result.error, ClientHttpProxyError)
    assert result.error.status == 407
