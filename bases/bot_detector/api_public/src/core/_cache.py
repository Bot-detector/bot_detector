import asyncio
import logging
from collections import OrderedDict

logger = logging.getLogger(__name__)


class SimpleALRUCache:
    def __init__(self, max_size=10_000):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.lock = asyncio.Lock()
        self.hits: int = 0
        self.misses: int = 0

    async def get(self, key):
        async with self.lock:
            if key in self.cache:
                # Move the accessed key to the end to mark it as recently used
                self.cache.move_to_end(key)
                self.hits += 1
                return self.cache[key]
            self.misses += 1
            return None

    async def put(self, key, value):
        async with self.lock:
            if key in self.cache:
                # Update the value and mark it as recently used
                self.cache.move_to_end(key)
                self.cache[key] = value
            else:
                # If the cache is full, remove the first (least recently used) item
                if len(self.cache) >= self.max_size:
                    self.cache.popitem(last=False)
                self.cache[key] = value

    async def clear(self):
        async with self.lock:
            self.cache.clear()


# Example usage
async def main():
    cache = SimpleALRUCache(max_size=3)

    await cache.put("a", 1)
    await cache.put("b", 2)
    await cache.put("c", 3)

    print(await cache.get("a"))  # Output: 1
    print(await cache.get("b"))  # Output: 2
    print(await cache.get("c"))  # Output: 3

    await cache.put("d", 4)  # This will evict 'a' because it's the LRU item

    print(await cache.get("a"))  # Output: None, 'a' has been evicted
    print(await cache.get("d"))  # Output: 4


if __name__ == "__main__":
    # Run the example
    asyncio.run(main())
