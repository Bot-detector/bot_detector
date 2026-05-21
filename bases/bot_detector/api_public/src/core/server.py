import logging
from contextlib import asynccontextmanager

from bot_detector.api_public.src import api
from bot_detector.api_public.src.core.fastapi.middleware import (
    LoggingMiddleware,
    PrometheusMiddleware,
    SecurityMiddleware,
)
from bot_detector.event_queue.adapters.kafka import (
    KafkaConfig,
    KafkaProducerConfig,
    KafkaSettings,
)
from bot_detector.event_queue.core import QueueProducer
from bot_detector.event_queue.factory import QueueFactory
from bot_detector.event_queue.structs import ReportsToInsertStruct
from fastapi import FastAPI
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import start_http_server

logger = logging.getLogger(__name__)


def init_routers(_app: FastAPI) -> None:
    _app.include_router(api.router)


def make_middleware() -> list[Middleware]:
    cors_config = {
        "allow_origins": [
            "http://osrsbotdetector.com",
            "https://osrsbotdetector.com",
            "http://localhost",
            "http://localhost:8080",
        ],
        "allow_credentials": True,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }

    middleware = [
        Middleware(SecurityMiddleware),
        Middleware(CORSMiddleware, **cors_config),
        Middleware(LoggingMiddleware),
        Middleware(PrometheusMiddleware),
    ]

    return middleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup initiated")
    queue = QueueFactory.create_queue(
        model=ReportsToInsertStruct,
        queue_type="producer",
        backend_type="kafka",
        config=KafkaConfig(
            topic="reports.to_insert",
            bootstrap_servers=KafkaSettings().bootstrap_servers,
            producer=True,
            producer_config=KafkaProducerConfig(partition_key_fn=None),
        ),
    )
    if isinstance(queue, Exception):
        raise queue
    assert isinstance(queue, QueueProducer)
    app.state.reports_to_insert_producer = queue
    producer = app.state.reports_to_insert_producer
    await producer.start()
    yield
    await producer.stop()
    logger.info("shutdown completed")


def create_app() -> FastAPI:
    _app = FastAPI(
        title="Bot-Detector-API",
        description="Bot-Detector-API",
        middleware=make_middleware(),
        lifespan=lifespan,
    )
    init_routers(_app=_app)
    return _app


app = create_app()


start_http_server(8000)


@app.get("/")
async def root():
    return {"message": "Hello World"}
