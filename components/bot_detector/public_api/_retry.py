import asyncio
import functools
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

import aiohttp

P = ParamSpec("P")
T = TypeVar("T")


class RetryableError(Exception):
    pass


def retry(
    max_attempts: int = 3,
    retry_on: tuple[type[Exception], ...] = (aiohttp.ClientConnectionError, RetryableError),
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exc: BaseException = RuntimeError(
                "retry exhausted with no exception"
            )
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except retry_on as e:
                    last_exc = e
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(2**attempt)
            raise last_exc

        return wrapper

    return decorator
