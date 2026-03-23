import aiohttp

from .structs import Err, Ok, Result


class ApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    async def _fetch(self, url: str, session: aiohttp.ClientSession) -> Result:
        try:
            async with session.get(url) as resp:
                resp.raise_for_status()
                return Ok(await resp.json())
        except Exception as e:
            return Err(e)

    async def get(self, path: str, session: aiohttp.ClientSession) -> Result:
        return await self._fetch(f"{self.base_url}{path}", session)
