import pathlib

import prometheus_client
from bot_detector.website import api
from bot_detector.website.core import Settings
from bot_detector.website.core.fastapi.middelware import (
    LoggingMiddleware,
    PrometheusMiddleware,
)
from fastapi import FastAPI, Request
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles


def init_routers(_app: FastAPI) -> None:
    _app.include_router(api.router)


def make_middleware() -> list[Middleware]:
    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        ),
        Middleware(LoggingMiddleware),
        Middleware(PrometheusMiddleware),
    ]
    return middleware


def create_app() -> FastAPI:
    _app = FastAPI(
        title="Bot-Detector-Web",
        description="Bot-Detector-Web",
        version=Settings().RELEASE_VERSION,
        middleware=make_middleware(),
    )
    init_routers(_app=_app)
    current_dir = pathlib.Path(__file__).parent
    parent_dir = current_dir.parent
    static_dir = pathlib.Path(parent_dir, "static")
    _app.mount("/static", StaticFiles(directory=static_dir), name="static")
    return _app


# uvicorn bases.bot_detector.website.core.server:app --port 5000 --reload
app = create_app()

prometheus_client.start_http_server(8000)


@app.get("/")
def root(request: Request):
    return RedirectResponse(request.url_for("home"))
