import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import orjson
from bot_detector.firehose.app.auth.auth import ANONYMOUS_USER, AuthUser
from bot_detector.firehose.app.metrics import QueueType, stream_type
from pydantic import BaseModel

QUEUE_MAX_SIZE = 1000


class InboxClosed(Exception):
    """The connection consumed too slow: its inbox was kicked."""


@dataclass
class Inbox:
    """Per-connection fan-out queue, registered under the conn_id.

    The QueueManager's pump fills the queue (via the Exchange); the
    route drains it. A full queue kicks the inbox: `kicked` is set,
    `kick` wakes parked getters, and the route must close the socket.
    """

    conn_id: str
    topic: str
    group: str
    user: AuthUser
    queue: asyncio.Queue = field(
        default_factory=lambda: asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
    )
    kicked: bool = False
    kick: asyncio.Event = field(default_factory=asyncio.Event)
    subscribed_at: float = field(default_factory=time.monotonic)

    @property
    def age_s(self) -> float:
        """Seconds since subscribe; drives the join grace in the exchange."""
        return time.monotonic() - self.subscribed_at

    @property
    def type(self) -> QueueType:
        """anonymous for the shared group, keyed for a discord user."""
        return stream_type(anonymous=self.user.name == ANONYMOUS_USER)

    async def get_message(
        self, disconnect: asyncio.Task[Any] | None = None
    ) -> str | InboxClosed | Any:
        """Next payload; InboxClosed once the connection was too slow.

        Races the queue against the kick flag so a parked getter wakes
        when the inbox is kicked. `disconnect` is the route's long-lived
        websocket.receive() task: when it completes first, its ASGI
        event is returned so the route can end the loop - otherwise an
        idle client disconnect would stay invisible until the next
        message.
        """
        get_task = asyncio.create_task(self.queue.get())
        kick_task = asyncio.create_task(self.kick.wait())
        # mixed task types; Any keeps the wait simple
        wait: set[asyncio.Task[Any]] = {get_task, kick_task}
        if disconnect is not None:
            wait.add(disconnect)
        done, pending = await asyncio.wait(wait, return_when=asyncio.FIRST_COMPLETED)
        # the disconnect task is long-lived: the route reuses it across
        # iterations, so never cancel it
        for task in pending:
            if task is not disconnect:
                task.cancel()
        await asyncio.gather(
            *(task for task in pending if task is not disconnect),
            return_exceptions=True,
        )
        if kick_task in done:
            return InboxClosed("consumed too slow")
        # a queued message wins over a completed receive task: the task
        # may merely hold a stale ASGI event (e.g. the handshake
        # "websocket.connect"), and the message is already popped from
        # the queue - returning it here would silently drop it
        if get_task in done:
            return get_task.result()
        if disconnect is not None and disconnect in done:
            return disconnect.result()
        return get_task.result()


def serialize(message: BaseModel) -> str:
    return orjson.dumps(message.model_dump()).decode("utf-8")
