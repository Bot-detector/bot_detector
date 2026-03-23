import time
from typing import Optional

from aiohttp import ClientSession
from bot_detector.rate_limiter import RateLimiter

from .exceptions import Err, Ok, PlayerDoesNotExist, Result, UnexpectedRedirection
from .structs import PlayerStats


class HiscoreOldSchoolAPI:
    url = "https://secure.runescape.com/m=hiscore_oldschool/index_lite.json"

    def __init__(self, rate_limiter: Optional[RateLimiter] = None) -> None:
        self.rate_limiter = rate_limiter if rate_limiter is not None else RateLimiter()

    async def _fetch(
        self,
        params: dict,
        session: ClientSession | None = None,
    ) -> Result:
        session = ClientSession() if session is None else session
        await self.rate_limiter.check()
        try:
            start_time = time.perf_counter()
            async with session.get(url=self.url, params=params) as resp:
                if resp.history and any(r.status == 302 for r in resp.history):
                    msg = f"{resp.url} - {resp.history[0].url}"
                    return Err(error=UnexpectedRedirection(msg))
                elif resp.status == 404:
                    msg = f"Player '{params['player']}' does not exist."
                    return Err(error=PlayerDoesNotExist(msg))
                elif resp.status != 200:
                    resp.raise_for_status()

                result = await resp.json()
            total_time = time.perf_counter() - start_time
            return Ok(value=result, latency=total_time)
        except Exception as e:
            return Err(error=e)

    def _transform(self, result: Ok) -> Result:
        try:
            stats = PlayerStats.model_validate(result.value)
            return Ok(value=stats, latency=result.latency)
        except Exception as e:
            return Err(error=e)

    async def get(self, player: str, session: ClientSession) -> Result:
        result = await self._fetch(params={"player": player}, session=session)

        if isinstance(result, Ok):
            return self._transform(result=result)
        return result
