from __future__ import annotations

import asyncio
import logging

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import (
    analysis,
    backends,
    config,
    events,
    features,
    proxy,
    rescan,
    routing,
    rules,
    sessions,
)
from .websocket import router as ws_router

logger = logging.getLogger("api.server")


def create_app() -> FastAPI:
    app = FastAPI(title="MCPSec API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(events.router)
    app.include_router(sessions.router)
    app.include_router(routing.router)
    app.include_router(analysis.router)
    app.include_router(config.router)
    app.include_router(proxy.router)
    app.include_router(backends.router)
    app.include_router(rules.router)
    app.include_router(features.router)
    app.include_router(rescan.router)
    app.include_router(ws_router)

    return app


async def start_api_server(app: FastAPI, host: str, port: int) -> None:
    config_obj = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        loop="none",
    )
    server = uvicorn.Server(config_obj)
    logger.info("API server running at http://%s:%d", host, port)
    await server.serve()
