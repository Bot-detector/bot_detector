import logging
import time

from aiohttp import ClientSession
from osrs.utils import RateLimiter
from pydantic import BaseModel

from .exceptions import RateLimitExceeded, Undefined, UnexpectedRedirection

logger = logging.getLogger(__name__)


class RuneMetricsError(BaseModel):
    error: str
    loggedIn: bool


class RuneMetricsPlayer(BaseModel):
    name: str
    rank: str | None
    totalskill: int
    totalxp: int
    combatlevel: int
    magic: int
    melee: int
    ranged: int
    questsstarted: int
    questscomplete: int
    questsnotstarted: int
    activities: list
    skillvalues: list
    loggedIn: bool


class RuneMetricsResponse(BaseModel):
    player: RuneMetricsPlayer | None = None
    error: RuneMetricsError | None = None


class RuneMetrics:
    BASE_URL = "https://apps.runescape.com/runemetrics/profile/profile"

    def __init__(
        self,
        proxy: str = "",
        rate_limiter: RateLimiter = RateLimiter(),
    ) -> None:
        self.proxy = proxy
        self.rate_limiter = rate_limiter

    async def get(
        self,
        player_name: str,
        session: ClientSession | None,
        return_latency: bool = False,
    ) -> RuneMetricsResponse | tuple[RuneMetricsResponse, float]:
        await self.rate_limiter.check()
        start_time = time.perf_counter()

        logger.debug(f"Performing runemetrics lookup on {player_name}")
        params = {"user": player_name}

        _session = ClientSession() if session is None else session

        async with _session.get(
            self.BASE_URL, proxy=self.proxy, params=params
        ) as response:
            # when the HS are down it will redirect to the main page.
            # after redirction it will return a 200, so we must check for redirection first
            if response.history and any(r.status == 302 for r in response.history):
                error_msg = (
                    f"Redirection occured: {response.url} - {response.history[0].url}"
                )
                raise UnexpectedRedirection(error_msg)
            elif response.status == 429:
                # raises ClientResponseError
                txt = await response.text()
                headers = response.headers
                msg = f"Response: {txt}, Headers: {headers}"
                raise RateLimitExceeded(message=msg)
            elif response.status != 200:
                # raises ClientResponseError
                response.raise_for_status()
                raise Undefined()

            data = await response.json()

        if session is None:
            await _session.close()

        _data = RuneMetricsResponse(
            player=RuneMetricsPlayer(**data) if "error" not in data else None,
            error=RuneMetricsError(**data) if "error" in data else None,
        )
        if return_latency:
            total_time = time.perf_counter() - start_time
            return _data, total_time
        return _data
