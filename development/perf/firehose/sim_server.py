"""Firehose server with QueueRepo patched to the fake kafka.

Profiling harness: runs the real firehose app (uvicorn, websockets,
metrics) against an in-process fake kafka that feeds realistic
ScrapedStruct payloads at a fixed rate.

Live views while it runs:
  http://127.0.0.1:5099/sim/dashboard   charts (polls /sim/metrics)
  http://127.0.0.1:5099/sim/metrics     prometheus exposition
  http://127.0.0.1:8099/metrics         raw registry (separate port)

Prefer the CLI:
  uv run --with pyinstrument python -m development.perf.firehose run \
      --n 20 --duration 50 --rate 20000 --profile-s 40

Outputs profile.html (interactive flame graph), profile.txt and
profile.json in the current directory when profiling is enabled.
"""

import asyncio
import importlib
import logging
import os
import time

os.environ.setdefault("BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("DATABASE_URL", "mysql+asyncmy://sim:sim@localhost/sim")

import uvicorn  # noqa: E402
from bot_detector.firehose.app.auth.auth import AuthUser  # noqa: E402
from bot_detector.firehose.app.consumer.queue_repo import QueueRepo  # noqa: E402
from bot_detector.firehose.core.config import Settings  # noqa: E402
from bot_detector.firehose.core.server import create_app  # noqa: E402
from fastapi.responses import HTMLResponse, Response  # noqa: E402
from prometheus_client import (  # noqa: E402
    CONTENT_TYPE_LATEST,
    REGISTRY,
    generate_latest,
)

from .dashboard import DASHBOARD_HTML  # noqa: E402
from .fake_kafka import FakeKafkaConsumer  # noqa: E402

CONSUMERS: dict[str, FakeKafkaConsumer] = {}
CONFIG = {
    "rate_s": 5000,
    "pool_size": 2000,
    "error_every": int(os.environ.get("SIM_ERROR_EVERY", "0") or 0),
    "poison_every": int(os.environ.get("SIM_POISON_EVERY", "0") or 0),
}


def create_consumer(self: QueueRepo, user: AuthUser, topic: str):
    group = self.resolve_consumer_group(user=user, topic=topic)
    if group not in CONSUMERS:
        print(
            f"[sim] first client for group={group}; starting feed "
            f"(rate={CONFIG['rate_s']}/s, pool={CONFIG['pool_size']}, "
            f"error_every={CONFIG['error_every']}, "
            f"poison_every={CONFIG['poison_every']})",
            flush=True,
        )
        CONSUMERS[group] = FakeKafkaConsumer(
            topic=topic,
            group=group,
            rate_s=CONFIG["rate_s"],
            pool_size=CONFIG["pool_size"],
            error_every=CONFIG["error_every"],
            poison_every=CONFIG["poison_every"],
        )
    return CONSUMERS[group]


# patch before create_app builds anything; the fake is duck-type
# compatible with the QueueConsumer surface the pump uses
QueueRepo.create_consumer = create_consumer  # type: ignore[assignment]


def add_sim_routes(app) -> None:
    @app.get("/sim/dashboard", include_in_schema=False)
    async def sim_dashboard() -> HTMLResponse:
        return HTMLResponse(DASHBOARD_HTML)

    @app.get("/sim/metrics", include_in_schema=False)
    async def sim_metrics() -> Response:
        return Response(
            content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST
        )


async def report() -> None:
    last: dict[str, tuple[int, int]] = {}
    t0 = time.monotonic()
    while True:
        await asyncio.sleep(5)
        now = time.monotonic()
        dt = now - t0
        t0 = now
        for g, c in CONSUMERS.items():
            if g in last:
                window = dt
            else:
                window = max(now - c.created, 1e-9)
            produced, consumed = last.get(g, (0, 0))
            last[g] = (c.produced_total, c.consumed_total)
            print(
                f"[sim] group={g} "
                f"produced={(c.produced_total - produced) / window:.0f}/s "
                f"consumed={(c.consumed_total - consumed) / window:.0f}/s "
                f"backlog={c.produced_total - c.consumed_total}",
                flush=True,
            )


def load_profiler():
    try:
        return importlib.import_module("pyinstrument").Profiler
    except ImportError as e:
        raise SystemExit(
            "pyinstrument is not installed; run with: "
            "uv run --with pyinstrument python -m development.perf.firehose run"
        ) from e


def serve(
    rate_s: int,
    pool_size: int,
    port: int,
    metrics_port: int,
    profile_s: int,
    verbose: bool = False,
) -> None:
    if not verbose:
        # app logs (connects, evictions) flood the terminal; the counts
        # are on the dashboard instead
        logging.getLogger("bot_detector").setLevel(logging.ERROR)
    CONFIG.update(rate_s=rate_s, pool_size=pool_size)
    app = create_app(settings=Settings(port=port, metrics_port=metrics_port))
    add_sim_routes(app)
    loop = asyncio.new_event_loop()
    loop.create_task(report())
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    print(
        f"[sim] firehose sim listening on ws://127.0.0.1:{port}/firehose/{{topic}} "
        f"(feed rate={rate_s}/s, pool={pool_size})",
        flush=True,
    )
    print(
        f"[sim] dashboard: http://127.0.0.1:{port}/sim/dashboard  "
        f"(consumers start on first client)",
        flush=True,
    )
    if profile_s > 0:
        Profiler = load_profiler()
        prof = Profiler(interval=0.001, async_mode="enabled")
        prof.start()

        async def dump_later() -> None:
            await asyncio.sleep(profile_s)
            prof.stop()
            with open("profile.html", "w") as f:
                f.write(prof.output_html())
            with open("profile.txt", "w") as f:
                f.write(prof.output_text(unicode=True, color=False, show_all=True))
            with open("profile.json", "w") as f:
                f.write(prof.output_json())
            print(
                "[sim] profile dumped to ./profile.html, ./profile.txt, ./profile.json",
                flush=True,
            )

        loop.create_task(dump_later())
    loop.run_until_complete(server.serve())


def main() -> None:
    serve(
        rate_s=int(os.environ.get("SIM_RATE_S", "5000")),
        pool_size=int(os.environ.get("SIM_POOL", "2000")),
        port=int(os.environ.get("SIM_PORT", "5099")),
        metrics_port=int(os.environ.get("SIM_METRICS_PORT", "8099")),
        profile_s=int(os.environ.get("SIM_PROFILE_S", "0")),
        verbose=os.environ.get("SIM_VERBOSE", "") == "1",
    )


if __name__ == "__main__":
    main()
