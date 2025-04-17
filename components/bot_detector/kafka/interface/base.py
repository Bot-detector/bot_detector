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
    async def get_lag(self):
        pass


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
