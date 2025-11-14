import asyncio
import logging
from collections import OrderedDict

logger = logging.getLogger(__name__)


class SimpleALRUCache:
    def __init__(self, max_size: int = 10_000):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.lock = asyncio.Lock()
        self.hits: int = 0
        self.misses: int = 0

    async def get(self, key):
        async with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                self.hits += 1
                return self.cache[key]
            self.misses += 1
            return None

    async def put(self, key, value):
        async with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                self.cache[key] = value
            else:
                if len(self.cache) >= self.max_size:
                    self.cache.popitem(last=False)
                self.cache[key] = value

    async def clear(self):
        async with self.lock:
            self.cache.clear()
