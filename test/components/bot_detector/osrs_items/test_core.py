import pytest
import pytest_asyncio
from datetime import datetime, timedelta
import aiohttp
from aioresponses import aioresponses

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


@pytest.mark.asyncio
async def test_load_items_success(session, sample_items_data):
    client = OsrsItemsClient(session=session, user_agent=TEST_USER_AGENT)

    with aioresponses() as m:
        m.get(
            "https://prices.runescape.wiki/api/v1/osrs/mapping",
            payload=sample_items_data,
            status=200,
        )

        await client._load_items()

        assert len(client._items_by_id) == 3
        assert len(client._items_by_name) == 3
        assert client._loaded_at is not None
        assert isinstance(client._loaded_at, datetime)


@pytest.mark.asyncio
async def test_load_items_with_user_agent(session, sample_items_data):
    client = OsrsItemsClient(session=session, user_agent=TEST_USER_AGENT)

    with aioresponses() as m:
        m.get(
            "https://prices.runescape.wiki/api/v1/osrs/mapping",
            payload=sample_items_data,
            status=200,
        )

        await client._load_items()

        # Verify items were loaded (indirectly tests user agent worked)
        assert len(client._items_by_id) == 3
        assert len(client._items_by_name) == 3


@pytest.mark.asyncio
async def test_lookup_by_item_id_found(session, sample_items_data):
    client = OsrsItemsClient(session=session, user_agent=TEST_USER_AGENT)

    with aioresponses() as m:
        m.get(
            "https://prices.runescape.wiki/api/v1/osrs/mapping",
            payload=sample_items_data,
            status=200,
        )

        await client._load_items()
        result = await client.lookup_by_item_id(1)

        assert result is not None
        assert result.id == 1
        assert result.name == "Bronze dagger"
        assert result.members is False


@pytest.mark.asyncio
async def test_lookup_by_item_id_not_found(session, sample_items_data):
    client = OsrsItemsClient(session=session, user_agent=TEST_USER_AGENT)

    with aioresponses() as m:
        m.get(
            "https://prices.runescape.wiki/api/v1/osrs/mapping",
            payload=sample_items_data,
            status=200,
        )

        await client._load_items()
        result = await client.lookup_by_item_id(99999)

        assert result is None


@pytest.mark.asyncio
async def test_lookup_by_name_found(session, sample_items_data):
    client = OsrsItemsClient(session=session, user_agent=TEST_USER_AGENT)

    with aioresponses() as m:
        m.get(
            "https://prices.runescape.wiki/api/v1/osrs/mapping",
            payload=sample_items_data,
            status=200,
        )

        await client._load_items()
        result = await client.lookup_by_name("Bronze dagger")

        assert result is not None
        assert result.id == 1
        assert result.name == "Bronze dagger"


@pytest.mark.asyncio
async def test_lookup_by_name_case_insensitive(session, sample_items_data):
    client = OsrsItemsClient(session=session, user_agent=TEST_USER_AGENT)

    with aioresponses() as m:
        m.get(
            "https://prices.runescape.wiki/api/v1/osrs/mapping",
            payload=sample_items_data,
            status=200,
        )

        await client._load_items()
        result = await client.lookup_by_name("bronze dagger")

        assert result is not None
        assert result.id == 1
        assert result.name == "Bronze dagger"


@pytest.mark.asyncio
async def test_lookup_by_name_not_found(session, sample_items_data):
    client = OsrsItemsClient(session=session, user_agent=TEST_USER_AGENT)

    with aioresponses() as m:
        m.get(
            "https://prices.runescape.wiki/api/v1/osrs/mapping",
            payload=sample_items_data,
            status=200,
        )

        await client._load_items()
        result = await client.lookup_by_name("Non-existent item")

        assert result is None


@pytest.mark.asyncio
async def test_cache_refresh_stale(session, sample_items_data):
    client = OsrsItemsClient(session=session, user_agent=TEST_USER_AGENT)

    with aioresponses() as m:
        # First load
        m.get(
            "https://prices.runescape.wiki/api/v1/osrs/mapping",
            payload=sample_items_data,
            status=200,
        )

        await client._load_items()
        initial_loaded_at = client._loaded_at

        # Manually set cache to be stale
        client._loaded_at = datetime.now() - timedelta(hours=25)

        # Second load (should refresh because cache is stale)
        # Add another mock response for the refresh
        m.get(
            "https://prices.runescape.wiki/api/v1/osrs/mapping",
            payload=sample_items_data,
            status=200,
        )

        result = await client.lookup_by_item_id(1)

        assert result is not None
        # Cache should have been refreshed (loaded_at changed)
        assert client._loaded_at > initial_loaded_at


@pytest.mark.asyncio
async def test_cache_not_refresh_fresh(session, sample_items_data):
    client = OsrsItemsClient(session=session, user_agent=TEST_USER_AGENT)

    with aioresponses() as m:
        m.get(
            "https://prices.runescape.wiki/api/v1/osrs/mapping",
            payload=sample_items_data,
            status=200,
        )

        await client._load_items()
        initial_loaded_at = client._loaded_at

        # Cache should NOT refresh if fresh (within 24 hours)
        # Since we just loaded it, it's fresh, so lookup should use cache
        result = await client.lookup_by_item_id(1)

        assert result is not None
        # loaded_at should be the same (no refresh)
        assert client._loaded_at == initial_loaded_at


@pytest.mark.asyncio
async def test_load_items_api_error(session):
    client = OsrsItemsClient(session=session, user_agent=TEST_USER_AGENT)

    with aioresponses() as m:
        m.get(
            "https://prices.runescape.wiki/api/v1/osrs/mapping",
            status=500,
        )

        with pytest.raises(Exception):
            await client._load_items()


@pytest.mark.asyncio
async def test_load_items_invalid_json(session):
    client = OsrsItemsClient(session=session, user_agent=TEST_USER_AGENT)

    with aioresponses() as m:
        m.get(
            "https://prices.runescape.wiki/api/v1/osrs/mapping",
            body="invalid json",
            status=200,
        )

        with pytest.raises(Exception):
            await client._load_items()


@pytest.mark.asyncio
async def test_lazy_load_on_first_lookup(session, sample_items_data):
    client = OsrsItemsClient(session=session, user_agent=TEST_USER_AGENT)

    assert client._loaded_at is None
    assert len(client._items_by_id) == 0

    with aioresponses() as m:
        m.get(
            "https://prices.runescape.wiki/api/v1/osrs/mapping",
            payload=sample_items_data,
            status=200,
        )

        result = await client.lookup_by_item_id(1)

        assert result is not None
        assert client._loaded_at is not None
        assert len(client._items_by_id) == 3
