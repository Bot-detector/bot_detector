from dataclasses import dataclass
from typing import Any


class Result:
    def is_ok(self):
        return isinstance(self, Ok)

    def is_err(self):
        return isinstance(self, Err)


@dataclass
class Ok(Result):
    value: Any


@dataclass
class Err(Result):
    error: Exception
