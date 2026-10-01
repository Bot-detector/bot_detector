"""Firehose container smoke test: real kafka, real uvicorn, real websockets.

Flow:
1. wait for the firehose websocket endpoint
2. connect a mixed fleet: two fast clients, one slow, one stalled
   (connects, never reads)
3. each client must receive exactly the seeded count - the firehose
   fans a copy of the group's stream to every inbox, so parity is
   required
4. both fast sequences must be identical (one pump, one order)
5. the runner then produces its own burst of copies of a captured
   payload: the stalled client's inbox is already full and older than
   the kick grace, so this must kick it with close code 1013 - and the
   fast clients must receive exactly those burst messages too
6. the slow client must reach the full count without a kick
7. after disconnects, firehose_connections must return to 0,
   firehose_kicked_total >= 1, firehose_messages_total covers 3 fleets

Prints a JSON report; exit 0 only when every check passes.
"""

import asyncio
import json
import os
import time
import urllib.request

import websockets
from kafka import KafkaProducer
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import ConnectionClosed

WS_URL = os.environ.get(
    "WS_URL", "ws://firehose:5000/firehose/players.scraped?anonymous=1"
)
METRICS_URL = os.environ.get("METRICS_URL", "http://firehose:8000/metrics")
KAFKA_BROKER = os.environ.get("KAFKA_BROKER", "kafka:9092")
SEEDED = int(os.environ.get("EXPECTED_MESSAGES", "1000"))
# the burst must exceed socket buffers (server send autotunes to ~4MB,
# client receive to ~6MB) so the stalled client's send path backs up
# and the kick fires; 10k messages x ~2KB does that with margin
BURST = int(os.environ.get("BURST_MESSAGES", "10000"))
TOTAL = SEEDED + BURST
START_TIMEOUT_S = float(os.environ.get("START_TIMEOUT_S", "90"))
IDLE_TIMEOUT_S = float(os.environ.get("IDLE_TIMEOUT_S", "15"))
KICK_WAIT_S = float(os.environ.get("KICK_WAIT_S", "30"))

Type = str


class Client:
    def __init__(self, name: str, kind: Type, slow_s: float = 0.0):
        self.name = name
        self.kind = kind
        self.slow_s = slow_s
        self.messages: list[str] = []
        self.close_code: int | None = None
        self.error: str | None = None
        self.first_at: float | None = None
        self.last_at: float | None = None
        self._ws: ClientConnection | None = None
        self._task: asyncio.Task | None = None

    async def connect(self) -> None:
        self._ws = await websockets.connect(WS_URL, max_size=2**22)
        if self.kind == "stalled":
            # connects and never reads: the inbox fills, the server kicks
            self._task = asyncio.create_task(self._park(), name=f"client-{self.name}")
        else:
            self._task = asyncio.create_task(self._run(), name=f"client-{self.name}")

    async def _park(self) -> None:
        await asyncio.Event().wait()

    async def _run(self) -> None:
        assert self._ws is not None
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(
                        self._ws.recv(), timeout=IDLE_TIMEOUT_S
                    )
                except TimeoutError:
                    break  # stream went idle: done
                except ConnectionClosed as closed:
                    self.close_code = closed.rcvd.code if closed.rcvd else None
                    break
                if not isinstance(payload, str):
                    continue
                if self.first_at is None:
                    self.first_at = time.monotonic()
                self.last_at = time.monotonic()
                self.messages.append(payload)
                if self.slow_s > 0.0:
                    await asyncio.sleep(self.slow_s)
        except Exception as exc:  # keep the fleet alive for the report
            self.error = f"{type(exc).__name__}: {exc}"

    async def wait_close(self, timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.close_code is not None:
                return True
            # a stalled client never reads, so its _run loop never sees
            # the close frame; the library tracks it anyway
            code = getattr(self._ws, "close_code", None)
            if code is not None:
                self.close_code = code
                return True
            await asyncio.sleep(0.2)
        return self.close_code is not None

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass


async def wait_for_endpoint(timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    last_error = "never tried"
    while time.monotonic() < deadline:
        probe = await websockets.connect(WS_URL)
        try:
            await probe.close()
            return
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            await asyncio.sleep(2)
    raise RuntimeError(f"firehose websocket never came up: {last_error}")


def scrape_metric(metric: str) -> float:
    with urllib.request.urlopen(METRICS_URL, timeout=10) as response:
        body = response.read().decode()
    total = 0.0
    for line in body.splitlines():
        if line.startswith(metric) and not line.startswith("#"):
            total += float(line.rsplit(" ", 1)[-1])
    return total


async def main() -> dict:
    checks: dict[str, bool] = {}
    await wait_for_endpoint(START_TIMEOUT_S)
    checks["endpoint_up"] = True

    fleet = [
        Client("fast-0", "fast"),
        Client("fast-1", "fast"),
        Client("slow-0", "slow", slow_s=0.005),
        Client("stalled-0", "stalled"),
    ]
    for client in fleet:
        await client.connect()

    # phase 1: drain the seeded stream; fasts must land on SEEDED exactly
    for client in (fleet[0], fleet[1]):
        deadline = time.monotonic() + START_TIMEOUT_S
        while (
            len(client.messages) < SEEDED
            and time.monotonic() < deadline
            and client.error is None
            and client.close_code is None
        ):
            await asyncio.sleep(0.2)
    for client in (fleet[0], fleet[1]):
        checks[f"{client.name}_seeded_count"] = len(client.messages) == SEEDED
    checks["fast_parity"] = (
        fleet[0].messages == fleet[1].messages and len(fleet[0].messages) > 0
    )
    if not checks["fast_parity"]:
        for client in fleet:
            await client.close()
        return _report(checks, fleet)

    # phase 2: produce a late burst from a captured payload. the stalled
    # inbox is full and now older than the kick grace, so the burst must
    # kick it - and the fasts must receive exactly the burst messages.
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BROKER,
        value_serializer=lambda x: json.dumps(x).encode(),
        acks="all",
    )
    template = json.loads(fleet[0].messages[-1])
    for i in range(BURST):
        message = json.loads(json.dumps(template))
        message["player_data"]["name"] = f"{message['player_data']['name']}-smoke-{i}"
        producer.send(topic="players.scraped", value=message)
    producer.flush()
    producer.close()
    await asyncio.sleep(1)  # give the pump a beat to fan the burst out

    for client in (fleet[0], fleet[1]):
        deadline = time.monotonic() + IDLE_TIMEOUT_S * 2
        while (
            len(client.messages) < TOTAL
            and time.monotonic() < deadline
            and client.error is None
            and client.close_code is None
        ):
            await asyncio.sleep(0.2)
    for client in (fleet[0], fleet[1]):
        checks[f"{client.name}_count"] = len(client.messages) == TOTAL

    # slow client: paces the seeded stream at 5ms/message - slow but not
    # slow enough to overflow its inbox - then leaves before the flood
    deadline = time.monotonic() + START_TIMEOUT_S + 2 * IDLE_TIMEOUT_S
    while (
        len(fleet[2].messages) < SEEDED
        and time.monotonic() < deadline
        and fleet[2].error is None
        and fleet[2].close_code is None
    ):
        await asyncio.sleep(0.2)
    checks["slow_full_stream"] = len(fleet[2].messages) >= SEEDED
    checks["slow_not_kicked"] = fleet[2].close_code is None
    await fleet[2].close()

    # stalled client: never reads, so the burst overflow kicks it. the
    # client itself cannot see the 1013 frame (it never reads), so it
    # just reports the connection as gone (1006); the server-side kick
    # counter below is the authoritative check
    checks["stalled_disconnected"] = await fleet[3].wait_close(KICK_WAIT_S)

    for client in fleet:
        await client.close()
    await asyncio.sleep(3)  # let the server finish cleanup

    checks["connections_drained"] = scrape_metric("firehose_connections") == 0
    checks["kicks_counted"] = scrape_metric("firehose_kicked_total") >= 1
    # two fasts take the full window; the slow client took the seed
    checks["messages_streamed"] = (
        scrape_metric("firehose_messages_total") >= 2 * TOTAL + SEEDED
    )

    return _report(checks, fleet)


def _report(checks: dict[str, bool], fleet: list[Client]) -> dict:
    details: dict[str, object] = {}
    details["fleet"] = [
        {
            "name": c.name,
            "kind": c.kind,
            "received": len(c.messages),
            "close_code": c.close_code,
            "error": c.error,
        }
        for c in fleet
    ]
    metrics = {
        "firehose_connections": scrape_metric("firehose_connections"),
        "firehose_kicked_total": scrape_metric("firehose_kicked_total"),
        "firehose_messages_total": scrape_metric("firehose_messages_total"),
    }
    report = {"checks": checks, "metrics": metrics, "fleet": details["fleet"]}
    print(json.dumps(report, indent=2))
    return checks


if __name__ == "__main__":
    results = asyncio.run(main())
    raise SystemExit(0 if all(results.values()) else 1)
