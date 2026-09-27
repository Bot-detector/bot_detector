"""Credential extraction dependencies (FastAPI security utilities)."""

from typing import Annotated

from fastapi import Security
from fastapi.security import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="Discord access token.",
)

ApiKey = Annotated[str | None, Security(API_KEY_HEADER)]
