import asyncio
import logging

from bot_detector.firehose.app.consumer import ALLOWED_TOPICS
from bot_detector.firehose.app.group_stream import serialize
from bot_detector.firehose.app.metrics import (
    FIREHOSE_BYTES,
    FIREHOSE_CONNECTIONS,
    FIREHOSE_MESSAGES,
    stream_type,
)
from bot_detector.firehose.app.state import FirehoseState
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["Firehose"])
logger = logging.getLogger(__name__)


@router.get("/firehose/topics", summary="Available firehose topics")
async def firehose_topics() -> list[str]:
    return ALLOWED_TOPICS


@router.websocket("/firehose/{topic}")
async def firehose(websocket: WebSocket, topic: str) -> None:
    if topic not in ALLOWED_TOPICS:
        await websocket.close(code=4404, reason="unknown topic")
        return

    # header for systems; ?token= for browsers (a websocket cannot set
    # headers from javascript). ?anonymous=1 forces the shared anonymous
    # group.
    force_anonymous = websocket.query_params.get("anonymous") == "1"
    api_key = None
    if not force_anonymous:
        api_key = websocket.headers.get("x-api-key") or websocket.query_params.get(
            "token"
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
    # anonymous streams fan out: this connection gets its own inbox and a
    # copy of every message; keyed streams compete on the shared queue
    # and rebroadcast to the group's connections. the client address
    # names the inbox for eviction logs
    client = websocket.client
    client_name = f"{client.host}:{client.port}" if client else None
    inbox = stream.subscribe(name=client_name)
    await state.connection_manager.connect(websocket=websocket, group=stream.group)
    FIREHOSE_CONNECTIONS.labels(topic=topic, type=conn_type).inc()
    logger.info(
        f"client connected topic={topic} group={stream.group} ({client_name=}, connections={state.connection_manager.count(group=stream.group)})"
    )
    try:
        while True:
            if inbox is not None:
                message = await inbox.queue.get()
            else:
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
            if inbox is None:
                await state.connection_manager.broadcast(
                    message=payload, group=stream.group
                )
    except WebSocketDisconnect:
        logger.info("client disconnected")
    except Exception:
        logger.exception("stream aborted")
    finally:
        FIREHOSE_CONNECTIONS.labels(topic=topic, type=conn_type).dec()
        stream.unsubscribe(inbox)
        state.connection_manager.disconnect(websocket=websocket)
        await state.consumer_manager.release(user=user, topic=topic)
