from abc import ABC, abstractmethod

from bot_detector.database.structs import PlayerStruct


class PlayersToScrapeConsumerInterface(ABC):
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
    async def consume_one(self) -> PlayerStruct:
        pass


class PlayersToScrapeProducerInterface(ABC):
    @abstractmethod
    def __init__(self, bootstrap_servers: list[str]):
        pass

    @abstractmethod
    async def start(self):
        pass

    @abstractmethod
    async def stop(self):
        pass

    @abstractmethod
    async def get_producer(self):
        pass

    @abstractmethod
    async def produce_one(self, value):
        pass
