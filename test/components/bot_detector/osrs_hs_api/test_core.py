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
