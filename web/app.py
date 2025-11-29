"""FastAPI application factory and main app.

This module creates the FastAPI application with all routers and
dependency injection configured.

Per docs/FRONTENDS.md, web routes are thin proxies to core APIs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

from openwrt_imagegen import __version__
from openwrt_imagegen.db import create_all_tables, get_engine, get_session_factory
from web.routers import builders, builds, config, flash, health, profiles

if TYPE_CHECKING:
    pass


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan context manager.

    Initializes database tables on startup.
    """
    engine = get_engine()
    create_all_tables(engine)
    app.state.session_factory = get_session_factory(engine)
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application.
    """
    application = FastAPI(
        title="OpenWrt Image Generator API",
        description="HTTP API for managing OpenWrt Image Builder profiles, "
        "builds, and TF/SD card flashing",
        version=__version__,
        lifespan=lifespan,
    )

    # Include routers
    application.include_router(health.router, tags=["health"])
    application.include_router(config.router, prefix="/config", tags=["config"])
    application.include_router(profiles.router, prefix="/profiles", tags=["profiles"])
    application.include_router(builders.router, prefix="/builders", tags=["builders"])
    application.include_router(builds.router, prefix="/builds", tags=["builds"])
    application.include_router(flash.router, prefix="/flash", tags=["flash"])

    return application


# Create the default application instance
app = create_app()
