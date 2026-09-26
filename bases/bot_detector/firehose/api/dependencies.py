"""Credential extraction dependencies (FastAPI security utilities)."""

from typing import Annotated

from fastapi import Depends, Request


def get_api_key_http(request: Request) -> str | None:
    """Resolve the credential for http endpoints.

    header wins, then ?token= (parity with websocket, which cannot set
    headers from a browser).
    """
    return request.headers.get("x-api-key") or request.query_params.get("token")


ApiKey = Annotated[str | None, Depends(get_api_key_http)]
