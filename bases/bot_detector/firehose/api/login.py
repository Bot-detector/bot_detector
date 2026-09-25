import logging
import secrets
from typing import Annotated, Optional

from bot_detector.firehose.api.dependencies import ApiKey
from bot_detector.firehose.app.auth.auth import ANONYMOUS_USER, API_KEY_COOKIE
from bot_detector.firehose.app.state import FirehoseState
from bot_detector.firehose.core.config import SETTINGS
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["Login"])
logger = logging.getLogger(__name__)

STATE_COOKIE = "discord_oauth_state"
STATE_MAX_AGE = 600  # seconds to complete the oauth flow
API_KEY_MAX_AGE = 7 * 24 * 3600


def get_state(request: Request) -> FirehoseState:
    state: FirehoseState = request.app.state.firehose
    return state


def _check_state(cookie_state: str | None, state: str | None) -> bool:
    if not cookie_state or not state:
        return False
    return secrets.compare_digest(cookie_state, state)


@router.get("/login", summary="Start the Discord OAuth2 flow")
async def login(request: Request) -> RedirectResponse:
    state = get_state(request)
    if state.discord_oauth is None:
        raise HTTPException(status_code=503, detail="oauth not configured")

    oauth_state = secrets.token_urlsafe(32)
    url = state.discord_oauth.authorization_url(
        redirect_uri=SETTINGS.discord_redirect_uri,
        scope="identify",
        state=oauth_state,
    )
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(
        key=STATE_COOKIE,
        value=oauth_state,
        max_age=STATE_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/login/callback", summary="Discord OAuth2 redirect target")
async def login_callback(
    request: Request,
    code: Annotated[Optional[str], Query()] = None,
    state: Annotated[Optional[str], Query()] = None,
    error: Annotated[Optional[str], Query()] = None,
) -> RedirectResponse:
    if error:
        raise HTTPException(status_code=400, detail=f"oauth error: {error}")

    cookie_state = request.cookies.get(STATE_COOKIE)
    if not _check_state(cookie_state=cookie_state, state=state):
        raise HTTPException(status_code=400, detail="state mismatch")
    if not code:
        raise HTTPException(status_code=400, detail="missing code")

    state_app = get_state(request)
    if state_app.discord_oauth is None:
        raise HTTPException(status_code=503, detail="oauth not configured")

    token = await state_app.discord_oauth.exchange_code(
        code=code, redirect_uri=SETTINGS.discord_redirect_uri
    )
    if isinstance(token, Exception):
        logger.warning(f"token exchange failed: {token}")
        raise HTTPException(status_code=502, detail="token exchange failed")

    user = await state_app.discord_oauth.get_current_user(
        access_token=token.access_token
    )
    if isinstance(user, Exception):
        logger.warning(f"fetch user failed: {user}")
        raise HTTPException(status_code=502, detail="fetch user failed")

    logger.info(f"discord login ok user={user.username} id={user.id}")

    # the discord access token IS the credential; the firehose validates
    # it against discord and the apiUser allowlist on every connect.
    # cookie: keeps the browser logged in; /me exposes identity + token.
    response = RedirectResponse("/me", status_code=302)
    response.set_cookie(
        key=API_KEY_COOKIE,
        value=token.access_token,
        max_age=API_KEY_MAX_AGE,
        samesite="lax",
    )
    return response


@router.get("/me", summary="Current identity for the browser session")
async def me(
    request: Request,
    api_key: ApiKey,
    topic: Annotated[str, Query()] = "players.scraped",
) -> dict[str, str | None | bool]:
    state = get_state(request)
    user = await state.auth_repo.authenticate(api_key=api_key, topic=topic)
    if api_key and isinstance(user, Exception):
        # a credential was presented but rejected -> 403 equivalent
        return {"user": ANONYMOUS_USER, "token": None, "allowed": False}
    if isinstance(user, Exception) or user.name == ANONYMOUS_USER:
        return {"user": ANONYMOUS_USER, "token": None, "allowed": True}
    return {"user": user.name, "token": api_key, "allowed": True}
