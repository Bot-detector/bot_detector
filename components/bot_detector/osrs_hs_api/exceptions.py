from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


class PlayerDoesNotExist(Exception):
    pass


class UnexpectedRedirection(Exception):
    pass


class Result(Generic[T]):
    def is_ok(self) -> bool:
        return isinstance(self, Ok)

    def is_err(self) -> bool:
        return isinstance(self, Err)


@dataclass
class Ok(Result[T], Generic[T]):
    value: T
    latency: float


@dataclass
class Err(Result[Exception]):
    error: Exception
    # wall time of the fetch attempt that produced this error; 0.0 when
    # the error was constructed without a fetch (tests, mocks)
    latency: float = 0.0
