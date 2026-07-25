from dataclasses import dataclass
from typing import Any, Union

from aiohttp.client_exceptions import ClientHttpProxyError
from pydantic import ValidationError


class PlayerDoesNotExist(Exception):
    pass


class UnexpectedRedirection(Exception):
    pass


class Result:
    def is_ok(self) -> bool:
        return isinstance(self, Ok)

    def is_err(self) -> bool:
        return isinstance(self, Err)


@dataclass
class Ok(Result):
    value: Any
    latency: float


@dataclass
class Err(Result):
    error: Union[
        PlayerDoesNotExist,
        UnexpectedRedirection,
        ClientHttpProxyError,
        ValidationError,
        Exception,
    ]
