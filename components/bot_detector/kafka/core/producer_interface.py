from abc import ABC, abstractmethod


class ProducerInterface(ABC):
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
