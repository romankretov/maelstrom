from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from . import logging_config, totp
from .auth import auth_backend, fastapi_users
from .config import get_settings
from .routes import (
    accounts,
    ai,
    backtests,
    health,
    live_strategies,
    markets,
    notifications,
    signals,
    strategies,
    ws_markets,
)
from .schemas import UserCreate, UserRead, UserUpdate

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging_config.configure(settings.log_level)
    log.info("api.startup", env=settings.env, domain=settings.domain)
    yield
    log.info("api.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Maelstrom API",
        version="0.0.1",
        lifespan=lifespan,
        default_response_class=ORJSONResponse,
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(health.router)
    app.include_router(
        fastapi_users.get_auth_router(auth_backend),
        prefix="/auth/jwt",
        tags=["auth"],
    )
    app.include_router(
        fastapi_users.get_register_router(UserRead, UserCreate),
        prefix="/auth",
        tags=["auth"],
    )
    app.include_router(
        fastapi_users.get_users_router(UserRead, UserUpdate),
        prefix="/users",
        tags=["users"],
    )
    app.include_router(totp.router)
    app.include_router(markets.router)
    app.include_router(strategies.router)
    app.include_router(backtests.router)
    app.include_router(accounts.router)
    app.include_router(live_strategies.router)
    app.include_router(ai.router)
    app.include_router(signals.router)
    app.include_router(notifications.router)
    app.include_router(ws_markets.router)
    return app
