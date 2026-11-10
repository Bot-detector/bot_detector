import logging
from collections.abc import Set as AbstractSet

from bot_detector.firehose.api.dependencies import ApiKey
from bot_detector.firehose.app.auth.auth import (
    ANONYMOUS_USER,
    WILDCARD_SCOPE,
)
from bot_detector.firehose.app.state import FirehoseState
from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["Me"])
logger = logging.getLogger(__name__)

SCOPE_PREFIX = "firehose."


class MeResponse(BaseModel):
    """Identity + the topics this identity may consume.

    - user None + allowed=false  -> invalid credential
    - user set + allowed=false   -> known identity, not allowlisted
    - anonymous                  -> allowed, every public topic (shared group)
    """

    user: str | None = None
    token: str | None = None
    allowed: bool
    topics: list[str] = []


def firehose_topics(scopes: list[str], streamable: AbstractSet[str]) -> list[str]:
    """Project `firehose.<topic>` scopes onto the streamable topics."""
    if WILDCARD_SCOPE in scopes:
        return sorted(streamable)
    return sorted(
        scope[len(SCOPE_PREFIX) :]
        for scope in scopes
        if scope.startswith(SCOPE_PREFIX) and scope[len(SCOPE_PREFIX) :] in streamable
    )


@router.get("/me", summary="Validate credential; return identity and topics")
async def me(request: Request, api_key: ApiKey) -> MeResponse:
    """Validate the credential, then report identity and allowed topics.

    - no credential  -> anonymous, allowed, every public topic (shared group)
    - bad credential -> allowed=false (invalid token or not allowlisted)
    - ok             -> identity + every topic the identity may consume
    """
    state: FirehoseState = request.app.state.firehose
    identity = await state.auth_repo.identify(api_key=api_key)
    if not identity.allowed:
        logger.info(f"credential rejected user={identity.user}")
        return MeResponse(user=identity.user, token=None, allowed=False, topics=[])
    if identity.user == ANONYMOUS_USER:
        topics = sorted(state.public_topics)
    else:
        topics = firehose_topics(
            identity.scopes, state.public_topics | state.keyed_topics
        )
    return MeResponse(user=identity.user, token=api_key, allowed=True, topics=topics)
