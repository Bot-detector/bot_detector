from abc import ABC, abstractmethod


class AbstractAPI(ABC):
    @abstractmethod
    def insert(self):
        raise NotImplementedError

    @abstractmethod
    def select(self):
        raise NotImplementedError

    @abstractmethod
    def update(self):
        raise NotImplementedError

    @abstractmethod
    def delete(self):
        raise NotImplementedError
