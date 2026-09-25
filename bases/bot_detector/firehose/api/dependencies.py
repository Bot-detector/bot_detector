"""Credential extraction dependencies (FastAPI security utilities)."""

from typing import Annotated

from bot_detector.firehose.app.auth.auth import (
    API_KEY_COOKIE,
    MANUAL_KEY_COOKIE,
)
from fastapi import Depends, Request
from fastapi.security import APIKeyCookie, APIKeyHeader, APIKeyQuery

# http-only: these security classes expect a Request and cannot be used
# on websocket routes
api_key_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query_scheme = APIKeyQuery(name="token", auto_error=False)
api_key_cookie_scheme = APIKeyCookie(name=API_KEY_COOKIE, auto_error=False)
manual_key_cookie_scheme = APIKeyCookie(name=MANUAL_KEY_COOKIE, auto_error=False)


async def get_api_key_http(request: Request) -> str | None:
    """Resolve the credential for http endpoints.

    header wins, then the manual cookie (dev frontend token field), then
    the discord login cookie.
    """
    return (
        request.headers.get("x-api-key")
        or request.cookies.get(MANUAL_KEY_COOKIE)
        or request.cookies.get(API_KEY_COOKIE)
    )


ApiKey = Annotated[str | None, Depends(get_api_key_http)]
