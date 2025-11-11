import asyncio
from collections import OrderedDict
from typing import Any


class SimpleALRUCache:
    """Async-safe LRU cache with a fixed max size."""

    def __init__(self, max_size: int = 10_000):
        self.cache: OrderedDict[str, Any] = OrderedDict()
        self.max_size = max_size
        self.lock = asyncio.Lock()
        self.hits: int = 0
        self.misses: int = 0

    async def get(self, key: str) -> Any:
        async with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                self.hits += 1
                return self.cache[key]
            self.misses += 1
            return None

    async def put(self, key: str, value: Any) -> None:
        async with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                self.cache[key] = value
            else:
                if len(self.cache) >= self.max_size:
                    self.cache.popitem(last=False)
                self.cache[key] = value

    async def clear(self) -> None:
        async with self.lock:
            self.cache.clear()
