import asyncio
import logging

from bot_detector.firehose.app.auth.auth import AuthUser
from bot_detector.firehose.app.exchange.structs import Inbox, InboxClosed
from bot_detector.firehose.app.metrics import FIREHOSE_KICKED

logger = logging.getLogger(__name__)

KICK_CODE = 1013
KICK_REASON = "inbox full"


class Exchange:
    """Global inbox registry, keyed by conn_id, grouped by (topic, group).

    Socket-free boundary between the QueueManager's kafka pumps and the
    api routes:

    - pumps push: inbox_ids() + send() copy each message into every
      inbox of a group; send never blocks and never raises - a full
      inbox is kicked and its route will see InboxClosed
    - routes drain: subscribe() -> get_inbox(conn_id) -> get_message()
    """

    def __init__(self) -> None:
        self._inboxes: dict[str, Inbox] = {}

    def subscribe(self, topic: str, group: str, conn_id: str, user: AuthUser) -> Inbox:
        """Register an empty inbox under the connection id."""
        inbox = Inbox(conn_id=conn_id, topic=topic, group=group, user=user)
        self._inboxes[conn_id] = inbox
        return inbox

    def get_inbox(self, conn_id: str) -> Inbox | InboxClosed:
        """The inbox for a connection; InboxClosed when kicked or gone."""
        inbox = self._inboxes.get(conn_id)
        if inbox is None or inbox.kicked:
            return InboxClosed("consumed too slow")
        return inbox

    def unsubscribe(self, conn_id: str | None) -> None:
        if conn_id is not None:
            self._inboxes.pop(conn_id, None)

    def get_subscribers(self, topic: str, group: str) -> list[str]:
        """conn_ids subscribed to this group; kicked inboxes excluded.

        An empty list means the group is gone: the QueueManager stops
        its queue and kafka retains the backlog.
        """
        return [
            conn_id
            for conn_id, inbox in self._inboxes.items()
            if inbox.topic == topic and inbox.group == group and not inbox.kicked
        ]

    def send(
        self, conn_id: str, topic: str, group: str, message: str | Exception
    ) -> None:
        """Push one copy into an inbox; never blocks, never raises.

        A full inbox is kicked (its route sees InboxClosed); an unknown,
        wrong-group or already-kicked conn_id is dropped. Backpressure
        is not the pump's problem.
        """
        inbox = self._inboxes.get(conn_id)
        if inbox is None or inbox.kicked:
            return
        if inbox.topic != topic or inbox.group != group:
            return
        try:
            inbox.queue.put_nowait(message)
        except asyncio.QueueFull:
            self._kick(inbox)

    async def send_or_wait(
        self, conn_id: str, topic: str, group: str, message: str | Exception
    ) -> None:
        """Send one copy, waiting while the LAST subscriber's inbox is full.

        A full inbox with other subscribers still connected kicks the
        slow one; the sole subscriber can never be kicked for
        backpressure - the pump waits instead (nobody else is held back,
        and kafka retains the stream). The wait also protects connect
        ramps: the first joiner is always the last subscriber.
        """
        while True:
            inbox = self._inboxes.get(conn_id)
            if inbox is None or inbox.kicked:
                return
            if inbox.topic != topic or inbox.group != group:
                return
            try:
                inbox.queue.put_nowait(message)
                return
            except asyncio.QueueFull:
                if len(self.get_subscribers(topic=topic, group=group)) > 1:
                    self._kick(inbox)
                    return
                await asyncio.sleep(0.05)

    def _kick(self, inbox: Inbox) -> None:
        """Flag a too-slow connection; its route closes the socket."""
        if inbox.kicked:
            return
        inbox.kicked = True
        FIREHOSE_KICKED.labels(topic=inbox.topic, type=inbox.type).inc()
        logger.warning(f"kicking inbox conn_id={inbox.conn_id} group={inbox.group}")
        inbox.kick.set()
