"""Fake firehose clients: an in-memory websocket fleet on the clock.

Port of perf's client fleet concepts (`run_clients`, the smoke
suite's slow/fast scenarios), rebuilt on DST so the exchange-side
behavior (fanout parity, join grace drops, kick with close 1013,
per-client ordering) is reproducible in virtual time:

- ``FirehoseHub`` is the exchange stand-in: ``send_all`` fans a
  payload out to per-client inboxes. On a full inbox it applies the
  same policy as the real Exchange: drop while the head is inside
  ``kick_grace_s``, kick (close 1013 "try again later") once it is
  older. Drops and kicks are counted, never silent.
- ``FirehoseClient`` is one connection: ``receive()`` yields payloads
  in order and wakes with a close frame when kicked mid-wait.
  ``slow_s`` adds a per-message virtual delay (the slow-client
  scenario) without needing a second machine: clients run on someone
  else's box, so their think-time is plain virtual sleep.

Scenarios drive sends and receives directly (no transport): the
websockets/uvicorn layer is what DST deliberately excludes; this fake
models its observable contract instead.
"""

import asyncio

from pydantic import BaseModel, Field

from ..clock import VirtualClock
from ..loop import running_clock

KICKED_CODE = 1013
KICKED_REASON = "try again later"
NORMAL_CLOSE = 1000


class FirehoseHubConfig(BaseModel):
    """Exchange-side policy, mirroring the firehose kick rules."""

    kick_grace_s: float = Field(default=30.0, gt=0.0)


class FirehoseClientConfig(BaseModel):
    """Per-connection shape: inbox size and per-message think time."""

    buffer_size: int = Field(default=1000, gt=0)
    slow_s: float = Field(default=0.0, ge=0.0)


class CloseFrame(BaseModel):
    """Terminal frame a receive() surfaces after close/kick."""

    code: int
    reason: str = ""


class ClientReport(BaseModel):
    """End-of-scenario totals for one client."""

    name: str
    received: int
    dropped: int
    close_code: int | None = None


class FirehoseClient:
    """One simulated websocket connection.

    ``receive()`` returns payloads in arrival order, or a CloseFrame
    once the hub closed the connection (kicked or client-closed). A
    ``slow_s`` delay applies per message; the inbox can still fill and
    kick while the client is thinking.
    """

    def __init__(
        self,
        name: str,
        config: FirehoseClientConfig,
        queue: "asyncio.Queue[bytes]",
        clock: VirtualClock,
    ):
        self.name = name
        self.config = config
        self.received_count = 0
        self.dropped_seen = 0
        self._queue = queue
        self._clock = clock
        self._kick = asyncio.Event()
        self._close_frame: CloseFrame | None = None

    @property
    def close_frame(self) -> CloseFrame | None:
        return self._close_frame

    async def receive(self) -> bytes | CloseFrame:
        """Wait for the next payload; a kick wakes the parked waiter."""
        while True:
            if self._close_frame is not None:
                return self._close_frame
            get_task = asyncio.create_task(self._queue.get())
            kick_task = asyncio.create_task(self._kick.wait())
            try:
                done, _pending = await asyncio.wait(
                    {get_task, kick_task}, return_when=asyncio.FIRST_COMPLETED
                )
            finally:
                for task in (get_task, kick_task):
                    if not task.done():
                        task.cancel()
            if kick_task in done:
                return self._close_frame if self._close_frame else self._kick_frame()
            payload = get_task.result()
            self.received_count += 1
            if self.config.slow_s > 0.0:
                await asyncio.sleep(self.config.slow_s)
            return payload

    def close(self) -> CloseFrame:
        """Client-side close (normal, code 1000)."""
        return self._apply_close(CloseFrame(code=NORMAL_CLOSE, reason="client closed"))

    def _kick_frame(self) -> CloseFrame:
        return self._apply_close(CloseFrame(code=KICKED_CODE, reason=KICKED_REASON))

    def _apply_close(self, frame: CloseFrame) -> CloseFrame:
        if self._close_frame is None:
            self._close_frame = frame
            self._kick.set()
        return self._close_frame


class _Inbox:
    """Hub-side per-client queue with head-age tracking for kicks."""

    def __init__(self, buffer_size: int):
        self.queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=buffer_size)
        self.head_enqueued_s: float | None = None

    def age_s(self, now_s: float) -> float:
        if self.head_enqueued_s is None:
            return 0.0
        return now_s - self.head_enqueued_s

    def put(self, payload: bytes, now_s: float) -> None:
        if self.queue.empty():
            self.head_enqueued_s = now_s
        self.queue.put_nowait(payload)

    def get(self, now_s: float) -> bytes:
        payload = self.queue.get_nowait()
        self.head_enqueued_s = None if self.queue.empty() else now_s
        return payload


class FirehoseHub:
    """Exchange stand-in: fanout with drop-then-kick backpressure.

    Binds to the running VirtualEventLoop's clock when constructed
    inside a ``dst.run`` scenario (same convention as Machine).
    """

    def __init__(self, config: FirehoseHubConfig, clock: VirtualClock | None = None):
        self.config = config
        self.clock = clock if clock is not None else running_clock()
        self._inboxes: dict[str, tuple[FirehoseClient, _Inbox]] = {}
        self.send_total = 0
        self.delivered_total = 0
        self.dropped_total = 0
        self.kicked_total = 0

    @property
    def clients(self) -> list[FirehoseClient]:
        return [client for client, _ in self._inboxes.values()]

    def connect(
        self, name: str, config: FirehoseClientConfig | None = None
    ) -> FirehoseClient:
        if name in self._inboxes:
            raise ValueError(f"client {name!r} already connected")
        client_config = config or FirehoseClientConfig()
        inbox = _Inbox(client_config.buffer_size)
        client = FirehoseClient(name, client_config, inbox.queue, self.clock)
        self._inboxes[name] = (client, inbox)
        return client

    def disconnect(self, name: str) -> None:
        client, _inbox = self._inboxes.pop(name)
        client.close()

    async def send_all(self, payload: bytes) -> int:
        """Fan a payload out to every inbox; returns delivered count.

        Full inboxes inside the grace window drop the message (counted
        via dropped_total); inboxes older than the grace kick their
        client with close 1013, exactly like the real Exchange.
        """
        self.send_total += 1
        delivered = 0
        for client, inbox in self._inboxes.values():
            if client.close_frame is not None:
                continue
            try:
                inbox.put(payload, self.clock.time())
                self.delivered_total += 1
                delivered += 1
            except asyncio.QueueFull:
                if inbox.age_s(self.clock.time()) > self.config.kick_grace_s:
                    client._kick_frame()
                    self.kicked_total += 1
                else:
                    self.dropped_total += 1
                    client.dropped_seen += 1
        return delivered

    def report(self) -> list[ClientReport]:
        return [
            ClientReport(
                name=client.name,
                received=client.received_count,
                dropped=client.dropped_seen,
                close_code=(client.close_frame.code if client.close_frame else None),
            )
            for client, _ in self._inboxes.values()
        ]


class FirehoseFleet:
    """Convenience over one hub: spawn/steer N named clients."""

    def __init__(self, hub: FirehoseHub):
        self.hub = hub

    def spawn(
        self,
        n: int,
        config: FirehoseClientConfig | None = None,
        *,
        prefix: str = "client",
    ) -> list[FirehoseClient]:
        return [self.hub.connect(f"{prefix}-{i}", config) for i in range(n)]

    def report(self) -> list[ClientReport]:
        return self.hub.report()
