import logging
from datetime import datetime
from typing import Any

import aiohttp
from pydantic import BaseModel

from bot_detector.osrs_items import OsrsItemsClient

logger = logging.getLogger(__name__)


class PredictionResponse(BaseModel):
    player_name: str
    prediction: float | None = None
    prediction_label: str | None = None
    created_at: datetime | None = None


class PlayerStats(BaseModel):
    player_id: int
    player_name: str
    reported: int = 0
    possible_ban: int = 0
    confirmed_ban: int = 0
    possible_ban_feedback: int = 0
    confirmed_ban_feedback: int = 0


class PublicApiClient:
    API_BASE_URL = "https://api-v2.prd.osrsbotdetector.com/api/v2"
    PRIVATE_API_BASE = "https://www.osrsbotdetector.com/api"

    def __init__(self, session: aiohttp.ClientSession, token: str | None = None):
        self.session = session
        self.token = token
        self.osrs_items: OsrsItemsClient | None = None

    def set_osrs_items(self, client: OsrsItemsClient):
        self.osrs_items = client

    async def _get(
        self,
        endpoint: str,
        params: dict | None = None,
        base_url: str | None = None,
    ) -> dict | list | None:
        url = f"{base_url or self.API_BASE_URL}{endpoint}"

        async with self.session.get(url, params=params) as resp:
            if resp.status == 404:
                return None
            if resp.status != 200:
                text = await resp.text()
                logger.error(f"API request failed: {resp.status} - {text}")
                raise RuntimeError(f"API request failed: {resp.status} - {text}")

            return await resp.json()

    async def _post(
        self,
        endpoint: str,
        json_data: Any = None,
        params: dict | None = None,
        base_url: str | None = None,
    ) -> Any:
        url = f"{base_url or self.API_BASE_URL}{endpoint}"

        async with self.session.post(url, json=json_data, params=params) as resp:
            if resp.status == 404:
                return None
            if resp.status not in (200, 201):
                text = await resp.text()
                logger.error(f"API POST failed: {resp.status} - {text}")
                raise RuntimeError(f"API POST failed: {resp.status} - {text}")

            return await resp.json()

    async def _get_list(
        self,
        endpoint: str,
        params: dict | None = None,
        base_url: str | None = None,
    ) -> Any:
        data = await self._get(endpoint, params, base_url)
        if isinstance(data, list):
            return data
        return None

    async def get_prediction(
        self,
        player_name: str,
        breakdown: bool = True,
    ) -> PredictionResponse | None:
        endpoint = "/player/prediction"
        params = {"name": player_name}

        if breakdown:
            params["breakdown"] = "true"

        data = await self._get(endpoint, params)

        if data is None or (isinstance(data, list) and len(data) == 0):
            return None

        prediction_data = data[0] if isinstance(data, list) else data

        return PredictionResponse(
            player_name=prediction_data.get("name", player_name),
            prediction=prediction_data.get("prediction"),
            prediction_label=prediction_data.get("label"),
            created_at=datetime.now(),
        )

    async def get_report_score(
        self,
        player_names: list[str],
    ) -> list[dict[str, Any]]:
        endpoint = "/player/report/score"
        params = {"name": ",".join(player_names)}

        data = await self._get(endpoint, params)
        if isinstance(data, list):
            return data
        return []

    async def get_feedback_score(
        self,
        player_names: list[str],
    ) -> list[dict[str, Any]]:
        endpoint = "/player/feedback/score"
        params = {"name": ",".join(player_names)}

        data = await self._get(endpoint, params)
        if isinstance(data, list):
            return data
        return []

    async def create_player(self, player_name: str) -> Any:
        endpoint = "/v1/player"
        params = {"player_name": player_name, "token": self.token}

        return await self._post(endpoint, params=params, base_url=self.PRIVATE_API_BASE)

    async def get_player(self, player_name: str) -> Any:
        endpoint = "/v1/player"
        params = {
            "player_name": player_name,
            "token": self.token,
            "row_count": 1,
            "page": 1,
        }

        data = await self._get(endpoint, params, base_url=self.PRIVATE_API_BASE)
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        return data

    async def get_discord_player(self, player_name: str) -> Any:
        endpoint = f"/discord/verify/player_rsn_discord_account_status/{self.token}/{player_name}"

        return await self._get_list(endpoint, base_url=self.PRIVATE_API_BASE)

    async def post_discord_code(
        self,
        discord_id: str,
        player_name: str,
        code: str,
    ) -> None:
        endpoint = f"/discord/verify/insert_player_dpc/{self.token}"
        json_data = {
            "discord_id": discord_id,
            "player_name": player_name,
            "code": code,
        }

        await self._post(endpoint, json_data=json_data, base_url=self.PRIVATE_API_BASE)

    async def get_discord_links(self, discord_id: str) -> Any:
        endpoint = f"/discord/get_linked_accounts/{self.token}/{discord_id}"

        return await self._get_list(endpoint, base_url=self.PRIVATE_API_BASE)

    async def get_project_stats(self) -> Any:
        endpoint = "/site/dashboard/projectstats"

        return await self._get_list(endpoint, base_url=self.PRIVATE_API_BASE)

    async def get_hiscore_latest(self, player_id: int) -> Any:
        endpoint = "/v1/hiscore/Latest"
        params = {"player_id": player_id, "token": self.token}

        return await self._get_list(endpoint, params, base_url=self.PRIVATE_API_BASE)

    async def get_contributions(
        self,
        player_ids: list[int],
        patreon: bool = False,
    ) -> Any:
        endpoint = "/stats/contributions/"
        params = {"token": self.token} if patreon else None

        return await self._post(
            endpoint,
            json_data=player_ids,
            params=params,
            base_url=self.PRIVATE_API_BASE,
        )

    async def get_heatmap_region(self, region_name: str) -> Any:
        endpoint = f"/discord/region/{self.token}"
        json_data = {"region_name": region_name}

        return await self._post(
            endpoint, json_data=json_data, base_url=self.PRIVATE_API_BASE
        )

    async def get_heatmap_data(self, region_id: int) -> Any:
        endpoint = f"/discord/heatmap/{self.token}"
        json_data = {"region_id": region_id}

        return await self._post(
            endpoint, json_data=json_data, base_url=self.PRIVATE_API_BASE
        )

    async def get_latest_sighting(self, player_name: str) -> Any:
        endpoint = f"/discord/get_latest_sighting/{self.token}"
        json_data = {"player_name": player_name}

        return await self._post(
            endpoint, json_data=json_data, base_url=self.PRIVATE_API_BASE
        )

    async def get_xp_gains(self, player_name: str) -> Any:
        endpoint = f"/discord/get_xp_gains/{self.token}"
        json_data = {"player_name": player_name}

        return await self._post(
            endpoint, json_data=json_data, base_url=self.PRIVATE_API_BASE
        )
