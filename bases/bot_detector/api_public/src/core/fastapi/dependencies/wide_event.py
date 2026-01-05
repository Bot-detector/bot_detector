from contextvars import ContextVar
from typing import Any

# The bucket that holds our wide event data
_log_context: ContextVar[dict[str, Any]] = ContextVar("log_context", default={})


def get_context() -> dict[str, Any]:
    return _log_context.get().copy()


def deep_merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge two dictionaries safely"""
    if not isinstance(a, dict) or not isinstance(b, dict):
        raise TypeError("Both arguments must be dicts")

    for key, value in b.items():
        if key in a and isinstance(a[key], dict) and isinstance(value, dict):
            deep_merge(a[key], value)
        else:
            a[key] = value
    return a


def add_context(data: dict[str, Any]):
    """
    Call this from anywhere in your app (routes, services, DB layer)
    to add context to the final wide event.
    """
    ctx = _log_context.get()
    ctx = deep_merge(ctx, data)
    _log_context.set(ctx)
