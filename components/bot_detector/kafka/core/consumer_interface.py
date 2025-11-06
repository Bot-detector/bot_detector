from abc import ABC, abstractmethod


class ConsumerInterface(ABC):
    @abstractmethod
    def __init__(self, group_id: str):
        pass

    @abstractmethod
    async def start(self):
        pass

    @abstractmethod
    async def stop(self):
        pass

    @abstractmethod
    async def get_consumer(self):
        pass

    @abstractmethod
    async def consume_one(self):
        pass

    @abstractmethod
    async def consume_many(self):
        pass

    @abstractmethod
    async def get_lag(self) -> int:
        pass
