"""Credential extraction dependencies (FastAPI security utilities)."""

from typing import Annotated

from bot_detector.firehose.app.auth.auth import ANONYMOUS_USER, AuthUser
from bot_detector.firehose.app.state import FirehoseState
from fastapi import Security, WebSocket, WebSocketException
from fastapi.security import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="Discord access token.",
)

ApiKey = Annotated[str | None, Security(API_KEY_HEADER)]


async def auth_user(websocket: WebSocket, topic: str) -> AuthUser:
    """Authenticate a websocket for the topic; the route's DI edge.

    Accepts the handshake first, so rejections arrive as websocket
    close frames (4401/4403) instead of an undifferentiated http 403.
    """
    await websocket.accept()
    state: FirehoseState = websocket.app.state.firehose
    # header for systems; ?token= for browsers (a websocket cannot set
    # headers from javascript). ?anonymous=1 forces the shared anonymous
    # group.
    force_anonymous = websocket.query_params.get("anonymous") == "1"
    api_key = None
    if not force_anonymous:
        api_key = websocket.headers.get("x-api-key") or websocket.query_params.get(
            "token"
        )
    user = await state.auth_repo.authenticate(api_key=api_key, topic=topic)
    if isinstance(user, Exception):
        raise WebSocketException(code=4401, reason="invalid api key")
    # keyed-only topics refuse the anonymous shared stream
    if user.name == ANONYMOUS_USER and topic in state.keyed_only_topics:
        raise WebSocketException(code=4403, reason="topic requires an api key")
    return user
