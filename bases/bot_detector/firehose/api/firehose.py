import asyncio
import logging

from bot_detector.firehose.app.consumer import ALLOWED_TOPICS
from bot_detector.firehose.app.exchange import InboxClosed, KICK_CODE, KICK_REASON
from bot_detector.firehose.app.metrics import (
    FIREHOSE_BYTES,
    FIREHOSE_CONNECTIONS,
    FIREHOSE_MESSAGES,
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

    queue = state.queue_manager.get(user=user, topic=topic)
    if isinstance(queue, Exception):
        logger.error(f"failed to create consumer: {queue}")
        await websocket.close(code=1011, reason="internal error")
        return

    conn_id = await state.connection_manager.connect(
        websocket=websocket, group=queue.group
    )
    inbox = state.exchange.subscribe(
        topic=topic,
        group=queue.group,
        conn_id=conn_id,
        user=user,
    )
    FIREHOSE_CONNECTIONS.labels(topic=topic, type=queue.type).inc()
    logger.info(
        f"client connected topic={topic} group={queue.group} "
        f"connection={conn_id} "
        f"(connections={state.connection_manager.count(group=queue.group)})"
    )
    try:
        # one long-lived receive task: get_message races it so an idle
        # client disconnect ends the loop immediately
        recv_task = asyncio.create_task(websocket.receive())
        while True:
            message = await inbox.get_message(disconnect=recv_task)
            if isinstance(message, InboxClosed):
                # too slow: the exchange kicked this inbox; close and
                # unsubscribe
                await state.connection_manager.close(
                    conn_id, code=KICK_CODE, reason=KICK_REASON
                )
                break
            if isinstance(message, dict):
                # ASGI event from the client
                if message.get("type") == "websocket.disconnect":
                    raise WebSocketDisconnect(code=message.get("code", 1000))
                if message.get("type") == "websocket.connect":
                    # uvicorn delivers the handshake event through
                    # receive: the long-lived receive task can complete
                    # with it before any message arrives, which would
                    # otherwise spin this loop and discard inbox
                    # messages. park a fresh receive and keep draining
                    recv_task = asyncio.create_task(websocket.receive())
                # stray client frame (ping/text); keep waiting
                continue
            if message is None:
                continue
            try:
                # the manager is the only socket interface: a send that
                # fails or times out leaves the socket unusable, so it
                # is closed, never retried
                await state.connection_manager.send(conn_id, payload=message)
            except Exception:
                await state.connection_manager.close(
                    conn_id, code=KICK_CODE, reason="send timeout"
                )
                break
            FIREHOSE_MESSAGES.labels(topic=topic, type=queue.type).inc()
            FIREHOSE_BYTES.labels(topic=topic, type=queue.type).inc(
                len(message.encode("utf-8"))
            )
    except WebSocketDisconnect:
        logger.info("client disconnected")
    except Exception:
        logger.exception("stream aborted")
    finally:
        recv_task.cancel()
        FIREHOSE_CONNECTIONS.labels(topic=topic, type=queue.type).dec()
        state.exchange.unsubscribe(conn_id)
        state.connection_manager.disconnect(conn_id)
        await state.queue_manager.release(user=user, topic=topic)
