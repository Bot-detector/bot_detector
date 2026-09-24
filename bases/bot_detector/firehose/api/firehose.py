import asyncio
import logging

from bot_detector.firehose.api.viewer import VIEWER_HTML
from bot_detector.firehose.app.auth.auth import API_KEY_COOKIE, MANUAL_KEY_COOKIE
from bot_detector.firehose.app.consumer import ALLOWED_TOPICS
from bot_detector.firehose.app.consumer_manager import serialize
from bot_detector.firehose.app.metrics import (
    FIREHOSE_BYTES,
    FIREHOSE_CONNECTIONS,
    FIREHOSE_MESSAGES,
    stream_type,
)
from bot_detector.firehose.app.state import FirehoseState
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Firehose"])
logger = logging.getLogger(__name__)


@router.get("/firehose", summary="Available firehose topics")
async def firehose_topics() -> HTMLResponse:
    items = "".join(
        f'<li><a href="/firehose/{topic}">{topic}</a></li>' for topic in ALLOWED_TOPICS
    )
    return HTMLResponse(
        f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Firehose topics</title></head>
<body style="font-family: monospace; background: #111; color: #ddd">
<h1>firehose topics</h1><ul>{items}</ul>
</body></html>"""
    )


@router.get("/firehose/{topic}", summary="Websocket viewer page for a topic")
async def firehose_page(topic: str) -> HTMLResponse:
    if topic not in ALLOWED_TOPICS:
        raise HTTPException(status_code=404, detail="unknown topic")
    return HTMLResponse(VIEWER_HTML)


@router.websocket("/firehose/{topic}")
async def firehose(websocket: WebSocket, topic: str) -> None:
    if topic not in ALLOWED_TOPICS:
        await websocket.close(code=4404, reason="unknown topic")
        return

    # header for systems; cookie for browsers (login cookie, or the
    # manual cookie set by the viewer's "connect with token" button).
    # ?anonymous=1 forces the shared anonymous group.
    force_anonymous = websocket.query_params.get("anonymous") == "1"
    api_key = None
    if not force_anonymous:
        api_key = (
            websocket.headers.get("x-api-key")
            or websocket.cookies.get(MANUAL_KEY_COOKIE)
            or websocket.cookies.get(API_KEY_COOKIE)
        )
    state: FirehoseState = websocket.app.state.firehose

    user = await state.auth_repo.authenticate(api_key=api_key, topic=topic)
    if isinstance(user, Exception):
        await websocket.close(code=4401, reason="invalid api key")
        return

    stream = state.consumer_manager.get(user=user, topic=topic)
    if isinstance(stream, Exception):
        logger.error(f"failed to create consumer: {stream}")
        await websocket.close(code=1011, reason="internal error")
        return

    conn_type = stream_type(anonymous=stream.anonymous)
    await state.connection_manager.connect(websocket=websocket, group=stream.group)
    FIREHOSE_CONNECTIONS.labels(topic=topic, type=conn_type).inc()
    logger.info(
        f"client connected topic={topic} group={stream.group} (connections={state.connection_manager.count(group=stream.group)})"
    )
    try:
        while True:
            message = await stream.get()
            if message is None:
                continue
            if isinstance(message, Exception):
                # skip poison messages / transient consumer errors
                # (backoff guards against a tight error loop)
                logger.warning(f"skipping message: {message}")
                await asyncio.sleep(0.5)
                continue
            payload = serialize(message)
            FIREHOSE_MESSAGES.labels(topic=topic, type=conn_type).inc()
            FIREHOSE_BYTES.labels(topic=topic, type=conn_type).inc(
                len(payload.encode("utf-8"))
            )
            await state.connection_manager.broadcast(
                message=payload, group=stream.group
            )
    except WebSocketDisconnect:
        logger.info("client disconnected")
    except Exception:
        logger.exception("stream aborted")
    finally:
        FIREHOSE_CONNECTIONS.labels(topic=topic, type=conn_type).dec()
        state.connection_manager.disconnect(websocket=websocket)
        await state.consumer_manager.release(user=user, topic=topic)
