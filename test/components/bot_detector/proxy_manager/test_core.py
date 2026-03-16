import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest
from bot_detector.proxy_manager import ProxyManager


@pytest.mark.asyncio
async def test_fetch_proxies():
    """
    Test the fetch_proxies method by calling the Webshare API and verifying the proxies list.
    """
    api_key = os.environ.get("PROXY_API_KEY")
    assert api_key, "API key not found in environment variables"

    proxy_manager = ProxyManager(api_key=api_key)
    await proxy_manager.fetch_proxies()
    proxies = await proxy_manager.get_proxy()

    print(f"Fetched {len(proxies)} proxies")
    assert len(proxies) > 0, "No proxies were fetched"


@pytest.mark.asyncio
async def test_get_proxy():
    """
    Test the get_proxy method for retrieving specific proxies or all proxies.
    """
    api_key = os.environ.get("PROXY_API_KEY")
    assert api_key, "API key not found in environment variables"

    proxy_manager = ProxyManager(api_key=api_key)
    await proxy_manager.fetch_proxies()

    all_proxies, error = await proxy_manager.get_proxy()
    assert error is None
    assert len(all_proxies) > 0

    # Fetch a specific proxy by index
    proxy, error = await proxy_manager.get_proxy(index=0)
    assert isinstance(proxy, str)
    assert proxy is not None, "Failed to retrieve proxy by index"


@pytest.mark.asyncio
async def test_rotate_proxies():
    """
    Test the rotate_proxies method to ensure it fetches a fresh list of proxies.
    """
    # there may or may not be rotation, we do not pay for manual rotation, but broken proxies will be rotated by the provider
    api_key = os.environ.get("PROXY_API_KEY")
    assert api_key, "API key not found in environment variables"

    proxy_manager = ProxyManager(api_key=api_key)

    # Fetch initial list of proxies
    await proxy_manager.fetch_proxies()
    proxies_before, error = await proxy_manager.get_proxy()
    assert error is None
    assert len(proxies_before) > 0

    # Rotate proxies
    await proxy_manager.rotate_proxies()
    proxies_after, error = await proxy_manager.get_proxy()
    assert error is None
    assert len(proxies_after) > 0

    assert len(proxies_before) == len(proxies_after)


@pytest.mark.asyncio
async def test_get_proxy_index_error():
    """
    Test the get_proxy method for retrieving specific proxies or all proxies.
    """
    api_key = os.environ.get("PROXY_API_KEY")
    assert api_key, "API key not found in environment variables"

    proxy_manager = ProxyManager(api_key=api_key)
    proxies = await proxy_manager.fetch_proxies()

    # Fetch a specific proxy by index
    proxy, error = await proxy_manager.get_proxy(index=len(proxies) + 1)
    assert isinstance(error, IndexError)
    assert proxy is None


@pytest.mark.asyncio
async def test_rotate_proxies_cooldown_skips_rapid_calls():
    """
    Test that rotate_proxies skips when called within cooldown window.
    """
    proxy_manager = ProxyManager(api_key="test-key", rotate_cooldown_seconds=10.0)

    with patch.object(
        proxy_manager, "fetch_proxies", new_callable=AsyncMock
    ) as mock_fetch:
        await proxy_manager.rotate_proxies()
        assert mock_fetch.call_count == 1

        await proxy_manager.rotate_proxies()
        assert mock_fetch.call_count == 1


@pytest.mark.asyncio
async def test_rotate_proxies_serializes_concurrent_calls():
    """
    Test that concurrent rotate_proxies calls are serialized via lock.
    With cooldown=0, each call will fetch (no coalescing).
    """
    proxy_manager = ProxyManager(api_key="test-key", rotate_cooldown_seconds=0.0)

    fetch_order = []

    async def fake_fetch():
        fetch_order.append("start")
        await asyncio.sleep(0.05)
        fetch_order.append("end")
        return ["http://proxy:8080"]

    with patch.object(proxy_manager, "fetch_proxies", side_effect=fake_fetch):
        await asyncio.gather(
            proxy_manager.rotate_proxies(),
            proxy_manager.rotate_proxies(),
            proxy_manager.rotate_proxies(),
        )

    assert len(fetch_order) == 6
    assert fetch_order == ["start", "end", "start", "end", "start", "end"]
