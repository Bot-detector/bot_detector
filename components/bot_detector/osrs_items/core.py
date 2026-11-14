import asyncio
from datetime import datetime, timedelta

import aiohttp
import orjson

from bot_detector.osrs_items.structs import ItemStruct


class OsrsItemsClient:
    API_URL = "https://prices.runescape.wiki/api/v1/osrs/mapping"
    CACHE_TTL_HOURS = 24
    REQUEST_TIMEOUT_S = 10

    def __init__(self, session: aiohttp.ClientSession, user_agent: str):
        self.session = session
        self.user_agent = user_agent
        self._items_by_id: dict[int, ItemStruct] = {}
        self._items_by_name: dict[str, ItemStruct] = {}
        self._loaded_at: datetime | None = None
        self._lock = asyncio.Lock()

    async def _load_items(self) -> None:
        headers = {"User-Agent": self.user_agent}

        async with self.session.get(
            self.API_URL,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT_S),
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Failed to load items: {resp.status}")

            data = orjson.loads(await resp.read())

        # parse fully before swapping; a bad payload must leave the old cache intact
        by_id: dict[int, ItemStruct] = {}
        by_name: dict[str, ItemStruct] = {}
        for item_data in data:
            item = ItemStruct(**item_data)
            by_id[item.id] = item
            by_name[item.name.lower()] = item

        self._items_by_id = by_id
        self._items_by_name = by_name
        self._loaded_at = datetime.now()

    def _is_stale(self) -> bool:
        if self._loaded_at is None:
            return False
        elapsed = datetime.now() - self._loaded_at
        return elapsed > timedelta(hours=self.CACHE_TTL_HOURS)

    async def _refresh_if_stale(self) -> None:
        if self._loaded_at is None or self._is_stale():
            async with self._lock:
                if self._loaded_at is None or self._is_stale():
                    await self._load_items()

    async def lookup_by_item_id(self, item_id: int) -> ItemStruct | None:
        await self._refresh_if_stale()
        return self._items_by_id.get(item_id)

    async def lookup_by_name(self, name: str) -> ItemStruct | None:
        await self._refresh_if_stale()
        name_lower = name.lower()
        return self._items_by_name.get(name_lower)
