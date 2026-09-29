"""Smoke test for the firehose sim server.

Starts the sim server as a subprocess (with injected errors and poison
messages), runs a mixed client fleet against it, scrapes the prometheus
metrics, and reports pass/fail per check as json.

Usage (from the repo root):
  python -m development.perf.firehose.smoke
  python -m development.perf.firehose.smoke --port 5100 --metrics-port 8100
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.request
from collections.abc import Sequence

import websockets
from websockets.exceptions import InvalidStatus

from .cli import wait_ready
from .clients import run_clients

METRIC_NAMES = (
    "firehose_consumers",
    "firehose_connections",
    "firehose_kicked_total",
)
KICK_CODE = 1013
STARTUP_TIMEOUT_S = 30.0
SETTLE_S = 2.0
MIN_FAST_MSGS = 10


def _fetch_metrics(metrics_port: int) -> str:
    with urllib.request.urlopen(
        f"http://127.0.0.1:{metrics_port}/metrics", timeout=10
    ) as resp:
        return resp.read().decode()


def _sum_metric(text: str, name: str) -> float:
    total = 0.0
    for line in text.splitlines():
        if line.startswith("#") or not line.startswith(name):
            continue
        rest = line[len(name) :]
        if rest[:1] not in ("{", " "):
            continue
        try:
            total += float(line.rsplit(" ", 1)[1])
        except (IndexError, ValueError):
            continue
    return total


def _msg_detail(clients: list[dict]) -> str:
    return f"msgs={[c['msgs'] for c in clients]}"


async def _handshake_rejected(url: str, headers: dict[str, str] | None = None) -> bool:
    """True when the server refuses the websocket upgrade (http 403).

    The routes close before accept for unknown topics and invalid api
    keys, which the ASGI server answers with a 403 handshake rejection
    instead of a websocket close frame.
    """
    try:
        async with websockets.connect(url, additional_headers=headers, max_size=None):
            pass
    except InvalidStatus:
        return True
    return False


def _build_checks(results: dict, metrics: dict[str, float]) -> list[dict]:
    clients: list[dict] = results["clients"]
    fast = [c for c in clients if c["kind"] == "fast"]
    slow = [c for c in clients if c["kind"] == "slow"]
    stalled = [c for c in clients if c["kind"] == "stalled"]
    healthy = fast + slow
    checks: list[dict] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": passed, "detail": detail})

    stalled_isolated = all(
        c["kicked"] and c["close_code"] == KICK_CODE for c in stalled
    ) or all(c["msgs"] == 0 for c in stalled)
    add(
        "stalled_clients_isolated",
        stalled_isolated,
        # a stall that begins before the client's first read fills the
        # inbox during the connect ramp and is kicked server-side; the
        # close frame cannot be observed by a client that never read,
        # so server-side kick counts are the evidence (kicks_counted)
        f"kicked={sum(1 for c in stalled if c['kicked'])}/{len(stalled)} "
        f"msgs={[c['msgs'] for c in stalled]} close_codes={[c['close_code'] for c in stalled]}",
    )
    add(
        "healthy_clients_not_kicked",
        not any(c["kicked"] for c in healthy),
        f"kicked={sum(1 for c in healthy if c['kicked'])}/{len(healthy)}",
    )
    add("fast_clients_received", all(c["msgs"] > 0 for c in fast), _msg_detail(fast))
    add("slow_clients_received", all(c["msgs"] > 0 for c in slow), _msg_detail(slow))
    add(
        "survived_poison_and_errors",
        all(c["msgs"] >= MIN_FAST_MSGS for c in fast),
        _msg_detail(fast) + f" (min={MIN_FAST_MSGS})",
    )
    ordered = [c for c in healthy if c["order_ok"]]
    add(
        "in_order_per_client",
        len(ordered) == len(healthy),
        f"in_order={len(ordered)}/{len(healthy)}",
    )

    consumers = metrics.get("firehose_consumers")
    add(
        "queues_cleaned_after_disconnect",
        consumers == 0.0,
        f"firehose_consumers={consumers}",
    )
    connections = metrics.get("firehose_connections")
    add(
        "connections_cleaned",
        connections == 0.0,
        f"firehose_connections={connections}",
    )
    kicked_total = metrics.get("firehose_kicked_total")
    add(
        "kicks_counted",
        kicked_total is not None and kicked_total >= 3,
        f"firehose_kicked_total={kicked_total}",
    )
    return checks


async def run_smoke(
    port: int = 5099, metrics_port: int = 8099, duration: float = 25.0
) -> dict:
    env = {
        **os.environ,
        "SIM_RATE_S": "200",
        "SIM_POOL": "200",
        "SIM_PORT": str(port),
        "SIM_METRICS_PORT": str(metrics_port),
        # fault rates sized so the routes' 0.5s error backoff stays well
        # below the message inflow: ~0.04 paused seconds per second
        "SIM_ERROR_EVERY": "4999",
        "SIM_POISON_EVERY": "997",
        "SIM_VERBOSE": "",
    }
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "development.perf.firehose.sim_server"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert proc.stdout is not None
    reader = asyncio.create_task(asyncio.to_thread(proc.stdout.read))

    checks: list[dict] = []
    results: dict | None = None
    metrics: dict[str, float] = {}
    startup_deadline = time.monotonic() + STARTUP_TIMEOUT_S
    while not await wait_ready(port=port, timeout_s=1.0):
        if proc.poll() is not None:
            checks.append(
                {
                    "name": "server_started",
                    "passed": False,
                    "detail": f"server exited during startup (code={proc.returncode})",
                }
            )
            break
        if time.monotonic() > startup_deadline:
            checks.append(
                {
                    "name": "server_started",
                    "passed": False,
                    "detail": f"server not ready after {STARTUP_TIMEOUT_S:.0f}s",
                }
            )
            break
    else:
        if proc.poll() is not None:
            checks.append(
                {
                    "name": "server_started",
                    "passed": False,
                    "detail": "server exited during startup",
                }
            )
        else:
            mix = ["fast"] * 12 + ["slow"] * 5 + ["stalled"] * 3
            results = await run_clients(
                n=len(mix),
                duration=duration,
                slow_ms=50,
                mix=mix,
                track_order=True,
                wrap=100,
                url=f"ws://127.0.0.1:{port}/firehose/players.scraped?anonymous=1",
            )
            base = f"ws://127.0.0.1:{port}/firehose"
            rejected_key = await _handshake_rejected(
                f"{base}/players.scraped", headers={"x-api-key": "not-a-token"}
            )
            rejected_topic = await _handshake_rejected(
                f"{base}/not.a.topic?anonymous=1"
            )
            await asyncio.sleep(SETTLE_S)
            try:
                text = await asyncio.to_thread(_fetch_metrics, metrics_port)
                metrics = {name: _sum_metric(text, name) for name in METRIC_NAMES}
            except OSError as e:
                checks.append(
                    {
                        "name": "metrics_scraped",
                        "passed": False,
                        "detail": f"{type(e).__name__}: {e}",
                    }
                )
            if results is not None:
                checks.extend(_build_checks(results=results, metrics=metrics))
            checks.append(
                {
                    "name": "bad_api_key_rejected",
                    "passed": rejected_key,
                    "detail": f"handshake_rejected={rejected_key}",
                }
            )
            checks.append(
                {
                    "name": "unknown_topic_rejected",
                    "passed": rejected_topic,
                    "detail": f"handshake_rejected={rejected_topic}",
                }
            )

    try:
        proc.terminate()
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    output = await reader
    crash_free = "stream aborted" not in output and "Traceback" not in output
    first_hit = next(
        (
            line
            for line in output.splitlines()
            if "stream aborted" in line or "Traceback" in line
        ),
        None,
    )
    checks.append(
        {
            "name": "no_server_crash",
            "passed": crash_free,
            "detail": "clean" if crash_free else f"first offender: {first_hit!r}",
        }
    )
    return {
        "checks": checks,
        "passed": all(check["passed"] for check in checks),
        "results": results,
        "metrics": metrics,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="firehose-smoke", description=__doc__)
    parser.add_argument("--port", type=int, default=5099)
    parser.add_argument("--metrics-port", type=int, default=8099)
    parser.add_argument("--duration", type=float, default=25.0)
    args = parser.parse_args(argv)
    report = asyncio.run(
        run_smoke(
            port=args.port, metrics_port=args.metrics_port, duration=args.duration
        )
    )
    print(json.dumps(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
