import logging
from contextlib import asynccontextmanager

import mlflow
from bot_detector.api_ml import api
from bot_detector.api_ml.core.config import SETTINGS, models
from bot_detector.api_ml.core.fastapi.middleware import (
    LoggingMiddleware,
    PrometheusMiddleware,
)
from fastapi import FastAPI
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import start_wsgi_server

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
    for name, uri in SETTINGS.MODEL_URIS.items():
        logger.info(f"Loading model: {name} from {uri}")
        model = mlflow.pyfunc.load_model(uri)
        assert model is not None
        models[name] = model
    logger.info(models.keys())

    logger.info("starting")
    yield
    logger.info("stopping")

    models.clear()
    print("Models unloaded")


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


start_wsgi_server(port=8000)


@app.get("/")
async def root():
    return {"message": "Hello World"}
