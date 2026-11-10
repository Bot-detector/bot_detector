import logging
from contextlib import asynccontextmanager

import uvicorn
from aiohttp import ClientSession
from bot_detector import logfmt  # noqa: F401  # configures root logging on import
from bot_detector.database.core import Settings as DatabaseSettings
from bot_detector.database.core import get_session_factory
from bot_detector.firehose.api import firehose, me
from bot_detector.firehose.app.auth.auth import ApiKeyAuthRepo
from bot_detector.firehose.app.auth.discord import DiscordOAuth
from bot_detector.firehose.app.connection_manager import ConnectionManager
from bot_detector.firehose.app.consumer import TOPIC_MODELS, keyed_only_topics
from bot_detector.firehose.app.consumer import QueueRepo
from bot_detector.firehose.app.exchange import Exchange
from bot_detector.firehose.app.queue_manager import QueueManager
from bot_detector.firehose.app.state import FirehoseState
from bot_detector.firehose.core.config import SETTINGS, Settings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import start_http_server

logger = logging.getLogger(__name__)


def init_routers(_app: FastAPI) -> None:
    _app.include_router(me.router)
    _app.include_router(firehose.router)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    state: FirehoseState = _app.state.firehose
    state.http_session = ClientSession()
    state.discord_oauth = DiscordOAuth(http=state.http_session)
    state.auth_repo.discord_oauth = state.discord_oauth
    # prometheus runs its own wsgi server on a separate port; scrapes
    # never touch the uvicorn loop serving the websockets
    metrics_server, metrics_thread = start_http_server(port=state.settings.metrics_port)
    yield
    metrics_server.shutdown()
    metrics_thread.join()
    await state.queue_manager.shutdown()
    await state.http_session.close()
    logger.info("shutdown complete")


def create_app(settings: Settings) -> FastAPI:
    _app = FastAPI(
        title="Bot-Detector-Firehose",
        description="Streams kafka messages over a websocket",
        lifespan=lifespan,
    )
    # the firehose frontend may run on another origin and select this
    # api as its endpoint; websockets are not cors-restricted, this
    # covers /me and /firehose/topics
    _app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["X-API-Key"],
    )
    queue_repo = QueueRepo(settings=settings)
    session_factory, _ = get_session_factory(DatabaseSettings())
    exchange = Exchange(grace_s=settings.kick_grace_s)
    # fail fast unless the access map covers the catalog exactly: a
    # missing entry silently publishes the topic to anonymous callers,
    # an unknown entry silently does nothing
    missing = set(TOPIC_MODELS) - set(settings.topic_access)
    if missing:
        raise ValueError(f"TOPIC_ACCESS is missing topics: {sorted(missing)}")
    unknown = set(settings.topic_access) - set(TOPIC_MODELS)
    if unknown:
        raise ValueError(f"TOPIC_ACCESS names unknown topics: {sorted(unknown)}")
    keyed_only = keyed_only_topics(topic_access=settings.topic_access)
    _app.state.firehose = FirehoseState(
        settings=settings,
        queue_repo=queue_repo,
        exchange=exchange,
        queue_manager=QueueManager(queue_repo=queue_repo, exchange=exchange),
        auth_repo=ApiKeyAuthRepo(session_factory=session_factory),
        connection_manager=ConnectionManager(),
        keyed_only_topics=keyed_only,
    )
    init_routers(_app=_app)
    return _app


app = create_app(settings=SETTINGS)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"message": "firehose"}


def run() -> None:
    uvicorn.run(
        "bot_detector.firehose.core.server:app",
        host=SETTINGS.host,
        port=SETTINGS.port,
    )


if __name__ == "__main__":
    run()
