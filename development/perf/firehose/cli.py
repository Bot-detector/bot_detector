"""CLI wrapper for the firehose profiling harness.

Usage (from the repo root):
  # one-shot: start sim server, run clients, collect profile, shut down
  uv run --with pyinstrument python -m development.perf.firehose run \
      --n 20 --duration 50 --rate 20000 --profile-s 40

  # replayable run: seeded payloads + seeded pct-based error/poison events
  python -m development.perf.firehose run --seed 42 --error-pct 0.5 --poison-pct 1

  # or piece by piece
  uv run --with pyinstrument python -m development.perf.firehose serve --rate 20000
  uv run python -m development.perf.firehose clients --n 20 --duration 50

Outputs profile.html (interactive flame graph), profile.txt and
profile.json in the current directory.
"""

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from .clients import run_clients

DEFAULT_PORT = 5099
DEFAULT_METRICS_PORT = 8099
DEFAULT_RATE = 5000
DEFAULT_POOL = 2000
DEFAULT_N = 20
DEFAULT_DURATION = 50
DEFAULT_SEED = 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="firehose-perf", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    serve = sub.add_parser("serve", help="start the simulated firehose server")
    serve.add_argument(
        "--rate", type=int, default=DEFAULT_RATE, help="messages/s fed per group"
    )
    serve.add_argument(
        "--pool", type=int, default=DEFAULT_POOL, help="distinct payloads pre-generated"
    )
    serve.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="RNG seed for payload pool + injected events (replayable)",
    )
    serve.add_argument(
        "--error-pct",
        type=float,
        default=0.0,
        help="%% of consumed messages returned as transient errors",
    )
    serve.add_argument(
        "--poison-pct",
        type=float,
        default=0.0,
        help="%% of consumed messages returned as poison (ValidationError)",
    )
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument("--metrics-port", type=int, default=DEFAULT_METRICS_PORT)
    serve.add_argument(
        "--profile-s",
        type=int,
        default=0,
        help="profile for N seconds then dump (0 = off)",
    )
    serve.add_argument(
        "--verbose",
        action="store_true",
        help="keep firehose app logs (connects, evictions)",
    )

    clients = sub.add_parser("clients", help="run anonymous websocket clients")
    clients.add_argument("--n", type=int, default=DEFAULT_N)
    clients.add_argument("--duration", type=float, default=DEFAULT_DURATION)
    clients.add_argument(
        "--slow-ms",
        type=float,
        default=0,
        help="per-message delay (slow-client scenario)",
    )
    clients.add_argument("--url", default=None, help="override ws endpoint")

    run = sub.add_parser("run", help="serve + clients + profile in one go")
    run.add_argument("--n", type=int, default=DEFAULT_N)
    run.add_argument("--duration", type=float, default=DEFAULT_DURATION)
    run.add_argument("--slow-ms", type=float, default=0)
    run.add_argument("--rate", type=int, default=DEFAULT_RATE)
    run.add_argument("--pool", type=int, default=DEFAULT_POOL)
    run.add_argument("--seed", type=int, default=DEFAULT_SEED)
    run.add_argument("--error-pct", type=float, default=0.0)
    run.add_argument("--poison-pct", type=float, default=0.0)
    run.add_argument("--port", type=int, default=DEFAULT_PORT)
    run.add_argument("--metrics-port", type=int, default=DEFAULT_METRICS_PORT)
    run.add_argument("--profile-s", type=int, default=0)
    run.add_argument("--verbose", action="store_true")

    return parser


async def wait_ready(port: int, timeout_s: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            await asyncio.to_thread(socket.create_connection, ("127.0.0.1", port), 1)
            return True
        except OSError:
            await asyncio.sleep(0.5)
    return False


async def cmd_run(args: argparse.Namespace) -> int:
    env = {
        **os.environ,
        "SIM_RATE_S": str(args.rate),
        "SIM_POOL": str(args.pool),
        "SIM_SEED": str(args.seed),
        "SIM_ERROR_PCT": str(args.error_pct),
        "SIM_POISON_PCT": str(args.poison_pct),
        "SIM_PORT": str(args.port),
        "SIM_METRICS_PORT": str(args.metrics_port),
        "SIM_PROFILE_S": str(args.profile_s),
        "SIM_VERBOSE": "1" if args.verbose else "",
    }
    t0 = time.monotonic()
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "development.perf.firehose.sim_server"],
        env=env,
    )
    try:
        # bail out as soon as the server process dies (e.g. port in
        # use, missing pyinstrument) instead of polling the full timeout
        while not await wait_ready(port=args.port, timeout_s=1.0):
            if proc.poll() is not None:
                print(
                    f"[run] server exited during startup (code={proc.returncode}); "
                    "check its output above",
                    flush=True,
                )
                return 1
        if proc.poll() is not None:
            print("[run] server exited during startup (port in use?)", flush=True)
            return 1
        print(
            f"[run] server ready — dashboard: http://127.0.0.1:{args.port}/sim/dashboard"
            f" (metrics: /sim/metrics), running {args.n} clients for "
            f"{args.duration:.0f}s",
            flush=True,
        )
        report = await run_clients(
            n=args.n,
            duration=args.duration,
            slow_ms=args.slow_ms,
            url=f"ws://127.0.0.1:{args.port}/firehose/players.scraped?anonymous=1",
        )
        print(json.dumps(report), flush=True)
        if args.profile_s > 0:
            remaining = args.profile_s + 3 - (time.monotonic() - t0)
            if remaining > 0:
                print(f"[run] waiting {remaining:.0f}s for profile dump", flush=True)
                await asyncio.sleep(remaining)
            cwd = Path.cwd()
            print(
                f"[run] artifacts: {cwd / 'profile.html'}, "
                f"{cwd / 'profile.txt'}, {cwd / 'profile.json'}",
                flush=True,
            )
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "serve":
        os.environ["SIM_SEED"] = str(args.seed)
        os.environ["SIM_ERROR_PCT"] = str(args.error_pct)
        os.environ["SIM_POISON_PCT"] = str(args.poison_pct)
        from . import sim_server

        sim_server.serve(
            rate_s=args.rate,
            pool_size=args.pool,
            port=args.port,
            metrics_port=args.metrics_port,
            profile_s=args.profile_s,
            verbose=args.verbose,
        )
        return 0
    if args.cmd == "clients":
        report = asyncio.run(
            run_clients(
                n=args.n, duration=args.duration, slow_ms=args.slow_ms, url=args.url
            )
        )
        print(json.dumps(report))
        return 0
    return asyncio.run(cmd_run(args=args))


if __name__ == "__main__":
    raise SystemExit(main())
