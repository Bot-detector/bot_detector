"""Anonymous firehose websocket clients.

Usage (from the repo root):
  python -m development.perf.firehose.clients --n 20 --duration 50
  python -m development.perf.firehose.clients --n 20 --duration 50 --slow-ms 250
  python -m development.perf.firehose.clients --n 4 --duration 10 \
      --mix fast,fast,slow,stalled

Client kinds:
  fast     recv as fast as the server pushes
  slow     recv, then sleep --slow-ms
  stalled  connect, never recv; inbox fills, server kicks with code 1013
"""

import argparse
import asyncio
import json
import math
import time
from collections.abc import Sequence

import websockets
from websockets.exceptions import ConnectionClosed, InvalidHandshake
from websockets.frames import Close

URL = "ws://127.0.0.1:5099/firehose/players.scraped?anonymous=1"
KINDS = ("fast", "slow", "stalled")
KICK_CODE = 1013


def _resolve_kinds(mix: Sequence[str] | None, n: int) -> list[str]:
    kinds = list(mix) if mix else ["fast"]
    return [kinds[i % len(kinds)] for i in range(n)]


def _new_record(index: int, kind: str) -> dict:
    return {
        "index": index,
        "kind": kind,
        "msgs": 0,
        "rate": 0.0,
        "kicked": False,
        "close_code": None,
        "close_reason": None,
        "error": None,
        "gap_p50_ms": 0.0,
        "gap_p99_ms": 0.0,
        "gap_max_ms": 0.0,
        "order_ok": True,
    }


def _percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, math.ceil(p / 100 * len(ordered)) - 1))
    return ordered[rank]


def _gap_stats(recv_at: list[float]) -> dict[str, float]:
    gaps = [b - a for a, b in zip(recv_at, recv_at[1:], strict=False)]
    return {
        "gap_p50_ms": round(_percentile(gaps, 50) * 1000, 3),
        "gap_p99_ms": round(_percentile(gaps, 99) * 1000, 3),
        "gap_max_ms": round(_percentile(gaps, 100) * 1000, 3),
    }


def _apply_close(rec: dict, rcvd: Close | None) -> None:
    if rcvd is None or rec["close_code"] is not None:
        return
    rec["close_code"] = rcvd.code
    rec["close_reason"] = rcvd.reason
    rec["kicked"] = rcvd.code == KICK_CODE


async def _hold_until_closed(ws: websockets.ClientConnection, deadline: float) -> None:
    remaining = deadline - time.monotonic()
    if remaining > 0:
        await asyncio.wait_for(ws.wait_closed(), timeout=remaining)


async def _client(
    index: int,
    kind: str,
    url: str,
    deadline: float,
    slow_ms: float,
    track_order: bool = False,
    wrap: int = 1000,
) -> dict:
    rec = _new_record(index, kind)
    delay = slow_ms / 1000
    recv_at: list[float] = []
    last_id: int | None = None
    try:
        ws = await websockets.connect(url, max_size=None)
    except (OSError, InvalidHandshake) as e:
        rec["error"] = f"{type(e).__name__}: {e}"
        return rec
    try:
        async with ws:
            if kind == "stalled":
                # read far slower than the stream: the inbox fills, the
                # server kicks, and the close frame is observed on the
                # next read (a never-reading client would buffer it all
                # client-side and never observe anything)
                while time.monotonic() < deadline:
                    await asyncio.sleep(2.0)
                    if time.monotonic() >= deadline:
                        break
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=5.0)
                        rec["msgs"] += 1
                    except (ConnectionClosed, TimeoutError):
                        break
            else:
                while time.monotonic() < deadline:
                    msg = await ws.recv()
                    recv_at.append(time.monotonic())
                    rec["msgs"] += 1
                    if track_order and isinstance(msg, str):
                        # the sim pool cycles deterministically through
                        # player ids; a small backwards jump is a real
                        # reorder/gap, a big one is a pool wrap
                        pid = json.loads(msg)["player_data"]["id"]
                        if last_id is not None and pid < last_id:
                            if (last_id - pid) < wrap:
                                rec["order_ok"] = False
                        last_id = pid
                    if delay:
                        await asyncio.sleep(delay)
    except ConnectionClosed as e:
        _apply_close(rec, e.rcvd)
    except TimeoutError:
        pass
    _apply_close(rec, getattr(ws.protocol, "rcvd", None))
    rec.update(_gap_stats(recv_at))
    return rec


async def run_clients(
    n: int,
    duration: float,
    slow_ms: float = 0,
    url: str | None = None,
    mix: list[str] | None = None,
    track_order: bool = False,
    wrap: int = 1000,
) -> dict:
    url = url or URL
    kinds = _resolve_kinds(mix=mix, n=n)
    deadline = time.monotonic() + duration
    tasks = [
        asyncio.create_task(_client(i, kind, url, deadline, slow_ms, track_order, wrap))
        for i, kind in enumerate(kinds)
    ]
    task_index = {task: i for i, task in enumerate(tasks)}
    done, pending = await asyncio.wait(tasks, timeout=duration + 10)
    for task in pending:
        task.cancel()

    records: dict[int, dict] = {}
    for task in done:
        if task.exception() is None:
            records[task_index[task]] = task.result()
    for i in range(n):
        if i not in records:
            rec = _new_record(i, kinds[i])
            rec["error"] = "client task did not finish"
            records[i] = rec

    clients = [records[i] for i in sorted(records)]
    for rec in clients:
        rec["rate"] = round(rec["msgs"] / duration, 2) if duration > 0 else 0.0
    return {
        "clients": clients,
        "total_msgs": sum(rec["msgs"] for rec in clients),
        "kicked": sum(1 for rec in clients if rec["kicked"]),
        "duration_s": duration,
    }


def _mix_arg(value: str) -> list[str]:
    kinds = [part.strip() for part in value.split(",") if part.strip()]
    bad = [kind for kind in kinds if kind not in KINDS]
    if not kinds or bad:
        raise argparse.ArgumentTypeError(
            f"invalid kind(s) {bad}; expected a csv of {KINDS}"
        )
    return kinds


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="firehose-clients", description=__doc__)
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--duration", type=float, default=40.0)
    parser.add_argument(
        "--slow-ms", type=float, default=0.0, help="per-message delay for slow clients"
    )
    parser.add_argument("--url", default=None, help="override ws endpoint")
    parser.add_argument(
        "--mix", type=_mix_arg, default=None, help="csv of kinds, cycled to --n"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = asyncio.run(
        run_clients(
            n=args.n,
            duration=args.duration,
            slow_ms=args.slow_ms,
            url=args.url,
            mix=args.mix,
        )
    )
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
