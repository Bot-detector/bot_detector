from datetime import datetime, timedelta

import aiohttp
from pydantic import BaseModel


class ItemStruct(BaseModel):
    id: int
    name: str
    examine: str | None = None
    members: bool
    lowalch: int | None = None
    highalch: int | None = None
    limit: int | None = None
    value: int | None = None
    icon: str | None = None


class OsrsItemsClient:
    API_URL = "https://prices.runescape.wiki/api/v1/osrs/mapping"
    CACHE_TTL_HOURS = 24

    def __init__(self, session: aiohttp.ClientSession, user_agent: str):
        self.session = session
        self.user_agent = user_agent
        self._items_by_id: dict[int, ItemStruct] = {}
        self._items_by_name: dict[str, ItemStruct] = {}
        self._loaded_at: datetime | None = None

    async def _load_items(self) -> None:
        headers = {"User-Agent": self.user_agent}

        async with self.session.get(self.API_URL, headers=headers) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Failed to load items: {resp.status}")

            data = await resp.json()

        self._items_by_id = {}
        self._items_by_name = {}

        for item_data in data:
            item = ItemStruct(**item_data)
            self._items_by_id[item.id] = item
            self._items_by_name[item.name.lower()] = item

        self._loaded_at = datetime.now()

    def _is_stale(self) -> bool:
        if self._loaded_at is None:
            return False
        elapsed = datetime.now() - self._loaded_at
        return elapsed > timedelta(hours=self.CACHE_TTL_HOURS)

    async def _refresh_if_stale(self) -> None:
        if self._loaded_at is None or self._is_stale():
            await self._load_items()

    async def lookup_by_item_id(self, item_id: int) -> ItemStruct | None:
        await self._refresh_if_stale()
        return self._items_by_id.get(item_id)

    async def lookup_by_name(self, name: str) -> ItemStruct | None:
        await self._refresh_if_stale()
        name_lower = name.lower()
        return self._items_by_name.get(name_lower)
