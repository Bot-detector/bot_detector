"""JSON-safe error serialization for wide events, dumped at the log site.

HTTP client exceptions carry rich structured attributes (status,
request url, response headers), but their repr() is a giant blob of
headers and cookies. dump_error() extracts the useful fields for the
classes we know and falls back to text for anything else.
"""

from typing import Any

import aiohttp

# all response headers are worth keeping except Set-Cookie: cookies
# must never land in logs.
_RESPONSE_HEADER_DENYLIST = frozenset({"set-cookie"})


def dump_error(error: Exception) -> dict[str, Any]:
    """JSON-safe error fields for wide events.

    Specific classes we know get structured fields; everything else
    falls back to text (str, or repr when the message is empty).
    """
    if isinstance(error, aiohttp.ClientResponseError):
        data: dict[str, Any] = {
            "type": type(error).__name__,
            "status": error.status,
            "message": error.message,
            "url": str(error.request_info.url),
            "method": error.request_info.method,
        }
        if error.headers:
            # str() flattens aiohttp istr keys: orjson rejects str
            # subclasses as dict keys ("Dict key must be str")
            data["headers"] = {
                str(key): value
                for key, value in error.headers.items()
                if key.lower() not in _RESPONSE_HEADER_DENYLIST
            }
        return data
    message = str(error).strip()
    if message:
        return {"type": type(error).__name__, "message": message}
    return {"type": type(error).__name__, "repr": repr(error)}
