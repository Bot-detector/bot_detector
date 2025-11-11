import asyncio
import logging
from typing import Optional

from aiohttp import ClientSession

from ..domain.settings import Settings
from ..dtos.proxy import Proxy

logger = logging.getLogger(__name__)


class ProxyManager:
    """Handles Webshare proxy rotation and caching."""

    def __init__(self, api_key: str) -> None:
        referral = "https://www.webshare.io/?referral_code=qvpjdwxqsblt"
        print(f"To get an API key, please use our referral code: {referral}")

        self.settings = Settings(PROXY_API_KEY=api_key)
        self.URL = "https://proxy.webshare.io/api/proxy/list/"
        self.proxy_list: list[str] = []
        self.lock = asyncio.Lock()

        if not api_key:
            raise ValueError("No API key provided")

    async def _fetch(
        self,
        session: ClientSession,
        url: str,
        headers: dict,
    ) -> tuple[list[Proxy], dict]:
        async with session.get(url, headers=headers) as response:
            response.raise_for_status()
            proxies: dict = await response.json()
            results = proxies.get("results", [])
            return [Proxy(**result) for result in results], proxies

    async def fetch_proxies(self) -> list[str]:
        headers = {"Authorization": f"Token {self.settings.PROXY_API_KEY}"}
        next_url: Optional[str] = self.URL
        discovered: list[Proxy] = []

        async with ClientSession() as session:
            while next_url:
                proxies, resp = await self._fetch(session, next_url, headers)
                discovered.extend(proxies)
                next_rel = resp.get("next")
                next_url = f"https://proxy.webshare.io{next_rel}" if next_rel else None
                logger.info("next_url=%s", next_url)

        async with self.lock:
            self.proxy_list = [proxy.url for proxy in discovered]
        return self.proxy_list

    async def get_proxy(self, index: Optional[int] = None):
        async with self.lock:
            if index is None:
                return list(self.proxy_list), None
            if not (0 <= index < len(self.proxy_list)):
                return None, IndexError("Proxy index out of range.")
            return self.proxy_list[index], None

    async def rotate_proxies(self) -> None:
        logger.info("Rotating proxies...")
        await self.fetch_proxies()
