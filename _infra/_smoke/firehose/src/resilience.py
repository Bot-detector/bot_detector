"""Resilience mode: broker bounce and consumer restart on the real stack.

aiokafka-level behavior that DST cannot model (group coordination,
reconnect backoff, offset commits):

1. two clients ride a paced 50 msg/s stream
2. the kafka container is restarted mid-stream: the consumer must
   reconnect on its own and resume; messages produced during the
   outage are retained by kafka and must arrive after rejoin
3. the firehose container is restarted mid-stream: the clients see
   their sockets drop, reconnect, and resume from the committed
   offsets; at-least-once delivery allows duplicates, so loss checks
   dedupe by player name

Exit 0 when every check passes.
"""

import asyncio
import json
import os
import time

import docker
import websockets
from kafka import KafkaProducer
from websockets.exceptions import ConnectionClosed

from smoke import Client

WS_URL = os.environ.get(
    "WS_URL", "ws://firehose:5000/firehose/players.scraped?anonymous=1"
)
KAFKA_BROKER = os.environ.get("KAFKA_BROKER", "kafka:9092")
KAFKA_CONTAINER = os.environ.get("KAFKA_CONTAINER", "kafka")
FIREHOSE_CONTAINER = os.environ.get("FIREHOSE_CONTAINER", "firehose")
DURATION_S = float(os.environ.get("RESILIENCE_DURATION_S", "150"))
FEED_RATE_S = float(os.environ.get("HUNT_FEED_RATE_S", "50"))
READ_TIMEOUT_S = 45.0  # survives the broker bounce without giving up


class ResilientClient(Client):
    """A client that reconnects through service restarts."""

    def __init__(self, name: str, deadline: float):
        super().__init__(name, "fast")
        self.deadline = deadline
        self.drops = 0
        self.names: set[str] = set()

    async def _run(self) -> None:
        assert self._ws is not None
        while time.monotonic() < self.deadline:
            try:
                payload = await asyncio.wait_for(
                    self._ws.recv(), timeout=READ_TIMEOUT_S
                )
            except asyncio.TimeoutError:
                continue  # broker may be down; keep the connection open
            except ConnectionClosed:
                self.drops += 1
                if not await self._reconnect():
                    return
                continue
            except Exception as exc:  # keep the fleet alive for the report
                self.error = f"{type(exc).__name__}: {exc}"
                return
            if not isinstance(payload, str):
                continue
            self.messages.append(payload)
            self.names.add(json.loads(payload)["player_data"]["name"])

    async def _reconnect(self) -> bool:
        while time.monotonic() < self.deadline:
            try:
                self._ws = await websockets.connect(WS_URL, max_size=2**22)
                return True
            except Exception:
                await asyncio.sleep(2)
        return False


async def restart_container(name: str, timeout_s: int = 10) -> None:
    # docker calls are blocking SDK round trips (a restart waits out the
    # container's graceful shutdown); keep them off the event loop so
    # the feed and clients keep running through the bounce
    await asyncio.to_thread(_restart_container_sync, name, timeout_s)


def _restart_container_sync(name: str, timeout_s: int) -> None:
    docker.from_env().containers.get(name).restart(timeout=timeout_s)


async def wait_container_healthy_async(name: str, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if await asyncio.to_thread(_container_healthy_sync, name):
            return
        await asyncio.sleep(2)
    raise RuntimeError(f"container {name} never became healthy")


def _container_healthy_sync(name: str) -> bool:
    container = docker.from_env().containers.get(name)
    container.reload()
    return container.health == "healthy"


async def produce_sustained(
    template: dict,
    producer: KafkaProducer,
    stop_event: asyncio.Event,
    names: set[str],
) -> int:
    """Pace FEED_RATE_S messages until stop_event; survives broker bounces.

    While the broker is down, sends fail and retry; nothing produced is
    ever counted twice, and arrivals during the outage are retained by
    kafka once it returns.
    """
    sent = 0
    errors = 0
    last_log = time.monotonic()
    slice_s = 0.2
    per_slice = max(1, int(FEED_RATE_S * slice_s))
    while not stop_event.is_set():
        slice_deadline = time.monotonic() + slice_s
        for _ in range(per_slice):
            if stop_event.is_set():
                break
            message = json.loads(json.dumps(template))
            name = f"res-{sent}"
            message["player_data"]["name"] = name
            try:
                # sync delivery off the event loop: the name only counts
                # once the broker acked it, so kafka-python's retries=0
                # default cannot turn a broker bounce into a phantom
                # "lost" message, and a down broker cannot stall the loop
                future = await asyncio.to_thread(
                    producer.send, topic="players.scraped", value=message
                )
                await asyncio.to_thread(future.get, 10)
                names.add(name)
                sent += 1
            except Exception as exc:
                errors += 1
                print(
                    f"[produce] error #{errors} at sent={sent}: "
                    f"{type(exc).__name__}: {exc}",
                    flush=True,
                )
                await asyncio.sleep(0.5)
                break
        now = time.monotonic()
        if now - last_log > 5:
            last_log = now
            print(f"[produce] sent={sent} errors={errors}", flush=True)
        await asyncio.sleep(max(0.0, slice_deadline - now))
    producer.flush()
    return sent


async def main() -> dict:
    checks: dict[str, bool] = {}
    deadline = time.monotonic() + DURATION_S
    fleet = [
        ResilientClient("res-0", deadline),
        ResilientClient("res-1", deadline),
    ]
    for client in fleet:
        await client.connect()

    # wait for the seeded stream to prove the pipe works, then grab a
    # payload as the producer template
    while len(fleet[0].messages) < 10 and time.monotonic() < deadline:
        await asyncio.sleep(0.2)
    template = json.loads(fleet[0].messages[0])

    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BROKER,
        value_serializer=lambda x: json.dumps(x).encode(),
        acks=1,
        # fail fast while the broker is down: the default 60s block per
        # send would stall the whole feed during the bounce
        max_block_ms=3000,
    )
    names: set[str] = set()
    stop_event = asyncio.Event()
    producer_task = asyncio.create_task(
        produce_sustained(template, producer, stop_event, names)
    )

    # phase 1: bounce kafka mid-stream
    baseline = [len(c.messages) for c in fleet]
    await restart_container(KAFKA_CONTAINER)
    await wait_container_healthy_async(KAFKA_CONTAINER, 120)
    resume_deadline = time.monotonic() + 90
    while time.monotonic() < resume_deadline:
        if all(len(c.messages) > baseline[i] for i, c in enumerate(fleet)):
            break
        await asyncio.sleep(0.5)
    checks["broker_bounce_resumed"] = all(
        len(c.messages) > baseline[i] for i, c in enumerate(fleet)
    )

    # phase 2: restart the firehose mid-stream; clients must reconnect
    baseline = [len(c.messages) for c in fleet]
    await restart_container(FIREHOSE_CONTAINER)
    await wait_container_healthy_async(FIREHOSE_CONTAINER, 120)
    resume_deadline = time.monotonic() + 90
    while time.monotonic() < resume_deadline:
        if all(len(c.messages) > baseline[i] for i, c in enumerate(fleet)):
            break
        await asyncio.sleep(0.5)
    checks["firehose_restart_reconnected"] = all(
        len(c.messages) > baseline[i] for i, c in enumerate(fleet)
    )

    # keep the feed going briefly, then wind down and drain to idle
    await asyncio.sleep(5)
    stop_event.set()
    produced = await producer_task
    drain_deadline = time.monotonic() + 60
    while time.monotonic() < drain_deadline:
        before = [len(c.messages) for c in fleet]
        await asyncio.sleep(3)
        if [len(c.messages) for c in fleet] == before:
            break

    for client in fleet:
        await client.close()

    counts = [len(c.messages) for c in fleet]
    checks["fleet_parity"] = counts[0] == counts[1]
    # at-least-once delivery allows duplicates; loss means a produced
    # name never arrived. received may also contain the seeded backlog
    checks["no_loss"] = names.issubset(fleet[0].names) and names.issubset(
        fleet[1].names
    )
    checks["clients_reconnected"] = all(c.drops >= 1 for c in fleet)

    report = {
        "mode": "resilience",
        "produced": produced,
        "produced_names": len(names),
        "received": counts,
        "unique_names": [len(c.names) for c in fleet],
        "drops": [c.drops for c in fleet],
        "checks": checks,
    }
    print(json.dumps(report, indent=2))
    return checks


if __name__ == "__main__":
    results = asyncio.run(main())
    raise SystemExit(0 if all(results.values()) else 1)
