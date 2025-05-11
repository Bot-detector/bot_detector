import logging
from contextlib import asynccontextmanager

from bot_detector.api_public.src import api
from bot_detector.api_public.src.core.fastapi.dependencies.kafka import kafka_manager
from bot_detector.api_public.src.core.fastapi.middleware import (
    LoggingMiddleware,
    PrometheusMiddleware,
)
from bot_detector.kafka import Settings as KafkaSettings
from bot_detector.kafka.repositories import RepoReportsToInsertProducer
from fastapi import FastAPI
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import start_http_server

logger = logging.getLogger(__name__)


def init_routers(_app: FastAPI) -> None:
    _app.include_router(api.router)


def make_middleware() -> list[Middleware]:
    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=[
                "http://osrsbotdetector.com/",
                "https://osrsbotdetector.com/",
                "http://localhost",
                "http://localhost:8080",
            ],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        ),
        Middleware(LoggingMiddleware),
        Middleware(PrometheusMiddleware),
    ]
    return middleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup initiated")
    kafka_manager.set_producer(
        key="reports_to_insert",
        producer=RepoReportsToInsertProducer(
            bootstrap_servers=KafkaSettings().KAFKA_BOOTSTRAP_SERVERS
        ),
    )
    producer = kafka_manager.get_producer(key="reports_to_insert")
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
