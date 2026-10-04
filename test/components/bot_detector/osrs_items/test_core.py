import asyncio
from datetime import datetime, timedelta

import aiohttp
import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer

from bot_detector.osrs_items.core import OsrsItemsClient

TEST_USER_AGENT = "test-user-agent"


@pytest_asyncio.fixture
async def session():
    async with aiohttp.ClientSession() as session:
        yield session


@pytest.fixture
def sample_items_data():
    return [
        {
            "id": 1,
            "name": "Bronze dagger",
            "examine": "A short dagger made of bronze.",
            "members": False,
            "lowalch": 1,
            "highalch": 2,
            "limit": 40,
            "value": 10,
            "icon": "bronze dagger.png",
        },
        {
            "id": 2,
            "name": "Bronze axe",
            "examine": "A woodcutter's axe made of bronze.",
            "members": False,
            "lowalch": 3,
            "highalch": 5,
            "limit": 40,
            "value": 16,
            "icon": "bronze axe.png",
        },
        {
            "id": 10344,
            "name": "3rd age amulet",
            "examine": "Fabulously ancient mage protection enchanted in the 3rd Age.",
            "members": True,
            "lowalch": 20200,
            "highalch": 30300,
            "limit": 8,
            "value": 50500,
            "icon": "3rd age amulet.png",
        },
    ]


def _build_app(responses: list) -> tuple[web.Application, dict]:
    """Serves /mapping returning each entry of `responses` in order.

    Entries: (status, payload) tuples or Exception instances to raise.
    The last entry repeats once exhausted.
    """
    state = {"call": 0}
    calls = {"n": 0}

    async def mapping(request: web.Request) -> web.Response:
        calls["n"] += 1
        idx = min(state["call"], len(responses) - 1)
        state["call"] += 1
        entry = responses[idx]
        if isinstance(entry, Exception):
            raise entry
        status, payload = entry
        if isinstance(payload, str):
            return web.Response(text=payload, status=status)
        return web.json_response(payload, status=status)

    app = web.Application()
    app.router.add_get("/api/v1/osrs/mapping", mapping)
    return app, calls


async def _start_client(
    session: aiohttp.ClientSession,
    user_agent: str,
    responses: list,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[OsrsItemsClient, TestServer, dict]:
    app, calls = _build_app(responses)
    server = TestServer(app)
    await server.start_server()
    monkeypatch.setattr(
        OsrsItemsClient, "API_URL", str(server.make_url("/api/v1/osrs/mapping"))
    )
    client = OsrsItemsClient(session=session, user_agent=user_agent)
    return client, server, calls


def _ok(payload) -> tuple[int, object]:
    return (200, payload)


@pytest.mark.asyncio
async def test_load_items_success(session, sample_items_data, monkeypatch):
    client, server, _ = await _start_client(
        session, TEST_USER_AGENT, [_ok(sample_items_data)], monkeypatch
    )
    try:
        await client._load_items()
        assert len(client._items_by_id) == 3
        assert len(client._items_by_name) == 3
        assert client._loaded_at is not None
        assert isinstance(client._loaded_at, datetime)
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_load_items_with_user_agent(session, sample_items_data, monkeypatch):
    client, server, app = await _start_client(
        session, TEST_USER_AGENT, [_ok(sample_items_data)], monkeypatch
    )
    try:
        await client._load_items()
        # Verify items were loaded (indirectly tests user agent worked)
        assert len(client._items_by_id) == 3
        assert len(client._items_by_name) == 3
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_lookup_by_item_id_found(session, sample_items_data, monkeypatch):
    client, server, _ = await _start_client(
        session, TEST_USER_AGENT, [_ok(sample_items_data)], monkeypatch
    )
    try:
        await client._load_items()
        result = await client.lookup_by_item_id(1)

        assert result is not None
        assert result.id == 1
        assert result.name == "Bronze dagger"
        assert result.members is False
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_lookup_by_item_id_not_found(session, sample_items_data, monkeypatch):
    client, server, _ = await _start_client(
        session, TEST_USER_AGENT, [_ok(sample_items_data)], monkeypatch
    )
    try:
        await client._load_items()
        result = await client.lookup_by_item_id(99999)

        assert result is None
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_lookup_by_name_found(session, sample_items_data, monkeypatch):
    client, server, _ = await _start_client(
        session, TEST_USER_AGENT, [_ok(sample_items_data)], monkeypatch
    )
    try:
        await client._load_items()
        result = await client.lookup_by_name("Bronze dagger")

        assert result is not None
        assert result.id == 1
        assert result.name == "Bronze dagger"
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_lookup_by_name_case_insensitive(session, sample_items_data, monkeypatch):
    client, server, _ = await _start_client(
        session, TEST_USER_AGENT, [_ok(sample_items_data)], monkeypatch
    )
    try:
        await client._load_items()
        result = await client.lookup_by_name("bronze dagger")

        assert result is not None
        assert result.id == 1
        assert result.name == "Bronze dagger"
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_lookup_by_name_not_found(session, sample_items_data, monkeypatch):
    client, server, _ = await _start_client(
        session, TEST_USER_AGENT, [_ok(sample_items_data)], monkeypatch
    )
    try:
        await client._load_items()
        result = await client.lookup_by_name("Non-existent item")

        assert result is None
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_cache_refresh_stale(session, sample_items_data, monkeypatch):
    client, server, _ = await _start_client(
        session, TEST_USER_AGENT, [_ok(sample_items_data)], monkeypatch
    )
    try:
        # First load
        await client._load_items()
        initial_loaded_at = client._loaded_at

        # Manually set cache to be stale
        client._loaded_at = datetime.now() - timedelta(hours=25)

        # Second load (should refresh because cache is stale)
        result = await client.lookup_by_item_id(1)

        assert result is not None
        # Cache should have been refreshed (loaded_at changed)
        assert client._loaded_at > initial_loaded_at
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_cache_not_refresh_fresh(session, sample_items_data, monkeypatch):
    client, server, calls = await _start_client(
        session, TEST_USER_AGENT, [_ok(sample_items_data)], monkeypatch
    )
    try:
        await client._load_items()
        initial_loaded_at = client._loaded_at
        requests_after_load = calls["n"]

        # Cache should NOT refresh if fresh (within 24 hours)
        result = await client.lookup_by_item_id(1)

        assert result is not None
        # loaded_at should be the same (no refresh)
        assert client._loaded_at == initial_loaded_at
        assert calls["n"] == requests_after_load
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_load_items_api_error(session, monkeypatch):
    client, server, _ = await _start_client(
        session, TEST_USER_AGENT, [(500, None)], monkeypatch
    )
    try:
        with pytest.raises(Exception):
            await client._load_items()
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_load_items_invalid_json(session, monkeypatch):
    client, server, _ = await _start_client(
        session, TEST_USER_AGENT, [_ok("invalid json")], monkeypatch
    )
    try:
        with pytest.raises(Exception):
            await client._load_items()
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_lazy_load_on_first_lookup(session, sample_items_data, monkeypatch):
    client, server, _ = await _start_client(
        session, TEST_USER_AGENT, [_ok(sample_items_data)], monkeypatch
    )
    try:
        assert client._loaded_at is None
        assert len(client._items_by_id) == 0

        result = await client.lookup_by_item_id(1)

        assert result is not None
        assert client._loaded_at is not None
        assert len(client._items_by_id) == 3
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_thundering_herd_only_one_request(
    session, sample_items_data, monkeypatch
):
    client, server, calls = await _start_client(
        session, TEST_USER_AGENT, [_ok(sample_items_data)], monkeypatch
    )
    try:
        client._loaded_at = datetime.now() - timedelta(hours=25)

        coros = [client.lookup_by_item_id(1) for _ in range(10)]
        results = await asyncio.gather(*coros)

        assert all(r is not None for r in results)
        assert len(client._items_by_id) == 3
        assert calls["n"] == 1
    finally:
        await server.close()
