from contextvars import ContextVar
from typing import Any

# The bucket that holds our wide event data
_log_context: ContextVar[dict[str, Any]] = ContextVar("log_context", default={})


def get_context() -> dict[str, Any]:
    return _log_context.get().copy()


def add_context(data: dict[str, Any]):
    """
    Call this from anywhere in your app (routes, services, DB layer)
    to add context to the final wide event.
    """
    ctx = _log_context.get()
    for key, value in data.items():
        if isinstance(value, dict) and isinstance(ctx.get(key), dict):
            # merge nested dict
            ctx[key].update(value)
        else:
            ctx[key] = value
