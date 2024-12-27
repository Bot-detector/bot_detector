import asyncio
import logging

from aiohttp import ClientSession
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class Ports(BaseModel):
    http: int
    socks5: int


class Proxy(BaseModel):
    username: str
    password: str
    proxy_address: str
    ports: Ports

    @property
    def url(self):
        """Constructs and returns the HTTP proxy URL."""
        return f"http://{self.username}:{self.password}@{self.proxy_address}:{self.ports.http}"


class ProxyManager:
    def __init__(self, api_key: str) -> None:
        """
        Initialize the Webshare API client.

        Args:
            api_key (str): API key for authenticating with Webshare.
        """
        referral = "https://www.webshare.io/?referral_code=qvpjdwxqsblt"
        print(f"To get an API key, please use our referral code: {referral}")

        self.URL = "https://proxy.webshare.io/api/proxy/list/"
        self.api_key = api_key
        self.proxy_list = []  # Holds the list of proxies
        self.lock = asyncio.Lock()  # Lock for thread-safe access to proxy list

        if not api_key:
            raise Exception("No API key provided")  # Ensure an API key is supplied

    async def _fetch(
        self, session: ClientSession, url: str, headers: dict
    ) -> tuple[list[Proxy], dict]:
        """
        Fetch proxy data from the Webshare API.

        Args:
            session (ClientSession): The aiohttp client session.
            url (str): The API endpoint URL.
            headers (dict): Headers for the API request.

        Returns:
            tuple: A tuple containing a list of Proxy objects and the raw JSON response.
        """
        async with session.get(url, headers=headers) as response:
            response.raise_for_status()  # Raise an error for HTTP response codes >= 400
            if response.status == 200:
                proxies: dict = await response.json()
                results = proxies.get("results", [])
                return [Proxy(**r) for r in results], proxies

    async def fetch_proxies(self):
        """
        Fetch all proxies from the Webshare API and update the proxy list.
        Handles pagination if the API returns multiple pages of results.
        """
        headers = {"Authorization": f"Token {self.api_key}"}
        next_url = self.URL
        _proxy_list = []

        async with ClientSession() as session:
            while next_url:
                proxies, resp = await self._fetch(session, next_url, headers)
                # Add proxy URLs to the local list
                _proxy_list.extend([proxy.url for proxy in proxies])

                # Check for the next page URL
                next = resp.get("next")
                next_url = f"https://proxy.webshare.io{next}" if next else None
                logger.info(f"{next_url=}")

        # Safely update the proxy list with a lock
        async with self.lock:
            self.proxy_list = _proxy_list
        return self.proxy_list

    async def get_proxy(self, index=None):
        """
        Retrieve a proxy by index or return all proxies if no index is specified.

        Args:
            index (int, optional): The index of the proxy to retrieve.

        Returns:
            str or list: A single proxy URL or the entire list of proxies.

        Raises:
            IndexError: If the index is out of range.
        """
        async with self.lock:
            if index is None:
                return list(self.proxy_list)  # Return a copy of the list

            if not (0 <= index < len(self.proxy_list)):
                raise IndexError("Proxy index out of range.")

            return self.proxy_list[index]

    async def rotate_proxies(self):
        """
        Rotate proxies by fetching a fresh list from the API.
        """
        logger.info("Rotating proxies...")
        await self.fetch_proxies()
