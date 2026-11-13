import asyncio
import time
from typing import Any, Optional

import aiohttp
from aiohttp import ClientSession, ClientTimeout
from bot_detector.rate_limiter import RateLimiter, Window
from pydantic import ValidationError

from .exceptions import Err, Ok, PlayerDoesNotExist, UnexpectedRedirection
from .structs import PlayerStats

DEFAULT_URL = "https://secure.runescape.com/m=hiscore_oldschool/index_lite.json"

# prod p99 is ~6s: draws past 10s fail anyway, so bound them instead of
# letting one stalled proxy pin a fetcher slot on aiohttp's 300s default
DEFAULT_TIMEOUT = ClientTimeout(total=10, connect=5)

# the edge serves the hiscores "down" page behind any redirect, not only 302
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

# timeouts and protocol failures are operational outcomes (Err values);
# anything else - TypeError, KeyError - is a bug and must surface
_FETCH_ERRORS = (aiohttp.ClientError, asyncio.TimeoutError, ValueError)


class HiscoreOldSchoolAPI:
    """Fetches and validates one player's hiscore lite JSON.

    The caller owns the ClientSession; this brick only drives it.
    Operational failures come back as Err values with the fetch's wall
    time. Rate-limiter failures propagate: the limiter is an injected
    scheduler, so its errors are bugs, not fetch outcomes.
    """

    def __init__(
        self,
        rate_limiter: Optional[RateLimiter] = None,
        url: str = DEFAULT_URL,
        timeout: ClientTimeout = DEFAULT_TIMEOUT,
    ) -> None:
        self.url = url
        self.timeout = timeout
        self.rate_limiter = (
            rate_limiter
            if rate_limiter is not None
            else RateLimiter(
                windows=[Window(name="default", count=60, interval_ms=60_000)]
            )
        )

    async def _fetch(
        self,
        player: str,
        session: ClientSession,
        proxy: Optional[str] = None,
    ) -> Ok[dict[str, Any]] | Err:
        """One rate-limited GET. Latency covers the request, not the wait."""
        await self.rate_limiter.check()
        start_time = time.perf_counter()
        try:
            async with session.get(
                url=self.url,
                params={"player": player},
                proxy=proxy,
                timeout=self.timeout,
            ) as resp:
                if any(r.status in REDIRECT_STATUSES for r in resp.history):
                    first = resp.history[0]
                    msg = (
                        f"unexpected redirect {first.status}: {first.url} -> {resp.url}"
                    )
                    return Err(
                        error=UnexpectedRedirection(msg),
                        latency=time.perf_counter() - start_time,
                    )
                if resp.status == 404:
                    msg = f"Player '{player}' does not exist."
                    return Err(
                        error=PlayerDoesNotExist(msg),
                        latency=time.perf_counter() - start_time,
                    )
                if resp.status != 200:
                    resp.raise_for_status()

                result = await resp.json()
            return Ok(value=result, latency=time.perf_counter() - start_time)
        except _FETCH_ERRORS as e:
            return Err(error=e, latency=time.perf_counter() - start_time)

    def _transform(self, result: Ok[dict[str, Any]]) -> Ok[PlayerStats] | Err:
        try:
            stats = PlayerStats.model_validate(result.value)
        except ValidationError as e:
            # the fetch still happened: its latency belongs on the error
            return Err(error=e, latency=result.latency)
        return Ok(value=stats, latency=result.latency)

    async def get(
        self, player: str, session: ClientSession, proxy: Optional[str] = None
    ) -> Ok[PlayerStats] | Err:
        result = await self._fetch(player=player, session=session, proxy=proxy)

        if isinstance(result, Ok):
            return self._transform(result=result)
        return result
