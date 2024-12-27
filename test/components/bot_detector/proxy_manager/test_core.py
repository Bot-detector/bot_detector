import os

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

    all_proxies = await proxy_manager.get_proxy()
    assert len(all_proxies) > 0

    # Fetch a specific proxy by index
    proxy = await proxy_manager.get_proxy(index=0)
    assert isinstance(proxy, str)
    assert proxy is not None, "Failed to retrieve proxy by index"


@pytest.mark.asyncio
async def test_rotate_proxies():
    """
    Test the rotate_proxies method to ensure it fetches a fresh list of proxies.
    """
    api_key = os.environ.get("PROXY_API_KEY")
    assert api_key, "API key not found in environment variables"

    proxy_manager = ProxyManager(api_key=api_key)

    # Fetch initial list of proxies
    await proxy_manager.fetch_proxies()
    proxies_before = await proxy_manager.get_proxy()
    assert len(proxies_before) > 0

    # Rotate proxies
    await proxy_manager.rotate_proxies()
    proxies_after = await proxy_manager.get_proxy()
    assert len(proxies_after) > 0

    assert len(proxies_before) == len(proxies_after)
    # there may or may not be rotation, we do not pay for manual rotation, but broken proxies will be rotated by the provider
