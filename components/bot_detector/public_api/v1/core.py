from typing import Any

import aiohttp
import orjson

from bot_detector.public_api._retry import retry
from bot_detector.public_api.v1.structs import (
    Bots,
    DiscordVerifyInfo,
    ExportInfo,
    PlayerName,
    RegionID,
    RegionName,
)
from bot_detector.rate_limiter import RateLimiter


class LegacyApiClient:
    DEFAULT_BASE_URL = "https://www.osrsbotdetector.com/api"

    def __init__(
        self,
        session: aiohttp.ClientSession,
        token: str,
        base_url: str | None = None,
        limiter: RateLimiter | None = None,
    ):
        self.session = session
        self.token = token
        self.base_url = base_url or self.DEFAULT_BASE_URL
        self.limiter = limiter or RateLimiter()

    @retry(max_attempts=3)
    async def get_project_stats(self) -> Any:
        await self.limiter.check()
        async with self.session.get(
            self.base_url + "/site/dashboard/projectstats",
        ) as res:
            res.raise_for_status()
            return orjson.loads(await res.read())

    @retry(max_attempts=3)
    async def verify_bot(self, bots: Bots) -> Any:
        await self.limiter.check()
        async with self.session.post(
            self.base_url + f"/site/verify/{self.token}",
            data=orjson.dumps(bots.model_dump()),
            headers={"Content-Type": "application/json"},
        ) as res:
            res.raise_for_status()
            return orjson.loads(await res.read())

    @retry(max_attempts=3)
    async def get_discord_verification_status(self, player_name: str) -> Any:
        await self.limiter.check()
        async with self.session.get(
            self.base_url
            + f"/discord/verify/player_rsn_discord_account_status/{self.token}/{player_name}",
        ) as res:
            res.raise_for_status()
            return orjson.loads(await res.read())

    @retry(max_attempts=3)
    async def get_verification_attempts(self, player_name: str) -> Any:
        await self.limiter.check()
        async with self.session.get(
            self.base_url
            + f"/discord/verify/get_verification_attempts/{self.token}/{player_name}",
        ) as res:
            res.raise_for_status()
            return orjson.loads(await res.read())

    @retry(max_attempts=3)
    async def post_verification_request(self, info: DiscordVerifyInfo) -> Any:
        await self.limiter.check()
        async with self.session.post(
            self.base_url + f"/discord/verify/insert_player_dpc/{self.token}",
            data=orjson.dumps(info.model_dump()),
            headers={"Content-Type": "application/json"},
        ) as res:
            res.raise_for_status()
            return orjson.loads(await res.read())

    @retry(max_attempts=3)
    async def get_linked_accounts(self, discord_id: int) -> Any:
        await self.limiter.check()
        async with self.session.get(
            self.base_url
            + f"/discord/get_linked_accounts/{self.token}/{discord_id}",
        ) as res:
            res.raise_for_status()
            return orjson.loads(await res.read())

    @retry(max_attempts=3)
    async def get_xp_gains(self, player_name: str) -> Any:
        await self.limiter.check()
        async with self.session.post(
            self.base_url + f"/discord/get_xp_gains/{self.token}",
            data=orjson.dumps(PlayerName(player_name=player_name).model_dump()),
            headers={"Content-Type": "application/json"},
        ) as res:
            res.raise_for_status()
            return orjson.loads(await res.read())

    @retry(max_attempts=3)
    async def get_latest_sighting(self, player_name: str) -> Any:
        await self.limiter.check()
        async with self.session.post(
            self.base_url + f"/discord/get_latest_sighting/{self.token}",
            data=orjson.dumps(PlayerName(player_name=player_name).model_dump()),
            headers={"Content-Type": "application/json"},
        ) as res:
            res.raise_for_status()
            return orjson.loads(await res.read())

    @retry(max_attempts=3)
    async def get_region(self, region_name: str) -> Any:
        await self.limiter.check()
        async with self.session.post(
            self.base_url + f"/discord/region/{self.token}",
            data=orjson.dumps(RegionName(region_name=region_name).model_dump()),
            headers={"Content-Type": "application/json"},
        ) as res:
            res.raise_for_status()
            return orjson.loads(await res.read())

    @retry(max_attempts=3)
    async def get_heatmap_data(self, region_id: int) -> Any:
        await self.limiter.check()
        async with self.session.post(
            self.base_url + f"/discord/heatmap/{self.token}",
            data=orjson.dumps(RegionID(region_id=region_id).model_dump()),
            headers={"Content-Type": "application/json"},
        ) as res:
            res.raise_for_status()
            return orjson.loads(await res.read())

    @retry(max_attempts=3)
    async def generate_player_bans_export(self, export: ExportInfo) -> Any:
        await self.limiter.check()
        async with self.session.post(
            self.base_url + f"/discord/player_bans/{self.token}",
            data=orjson.dumps(export.model_dump()),
            headers={"Content-Type": "application/json"},
        ) as res:
            res.raise_for_status()
            return orjson.loads(await res.read())

    @retry(max_attempts=3)
    async def download_export(self, export_id: str) -> Any:
        await self.limiter.check()
        async with self.session.get(
            self.base_url + f"/discord/download_export/{export_id}",
        ) as res:
            res.raise_for_status()
            return orjson.loads(await res.read())
