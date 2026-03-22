"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI

from etelemetry_server.allowlist import load_allowlist, sync_allowlist_to_db
from etelemetry_server.db import async_session_factory, engine, init_db
from etelemetry_server.settings import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown resources."""
    # --- Startup ---
    # Store settings on app state for easy access
    app.state.settings = settings
    app.state.engine = engine

    # Initialise database tables (dev convenience; prod uses Alembic)
    await init_db()

    # Load GeoIP reader if the database file exists
    app.state.geoip_reader = None
    geoip_path = Path(settings.MAXMIND_DB_PATH)
    if geoip_path.exists():
        try:
            import geoip2.database

            app.state.geoip_reader = geoip2.database.Reader(str(geoip_path))
            logger.info("GeoIP database loaded from %s", geoip_path)
        except Exception:
            logger.warning("Failed to load GeoIP database", exc_info=True)
    else:
        logger.info("GeoIP database not found at %s; skipping", geoip_path)

    # Load allowlist and sync to DB
    allowlist = load_allowlist(settings.ALLOWLIST_PATH)
    app.state.allowlist = allowlist
    if allowlist:
        async with async_session_factory() as session:
            await sync_allowlist_to_db(session, allowlist)
            await session.commit()
        logger.info("Synced %d allowlist entries to database", len(allowlist))

    yield

    # --- Shutdown ---
    if app.state.geoip_reader is not None:
        app.state.geoip_reader.close()

    await engine.dispose()


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    app = FastAPI(
        title="etelemetry",
        description="Version-check telemetry service",
        version="2.0.0",
        lifespan=lifespan,
    )

    # --- Compression middleware ---
    try:
        from starlette_compress import CompressMiddleware

        app.add_middleware(CompressMiddleware)
    except ImportError:
        from starlette.middleware.gzip import GZipMiddleware

        app.add_middleware(GZipMiddleware, minimum_size=500)

    # --- Route routers ---
    try:
        from etelemetry_server.routes.health import router as health_router

        app.include_router(health_router)
    except ImportError:
        logger.debug("health router not yet available")

    try:
        from etelemetry_server.routes.projects import router as projects_router

        app.include_router(projects_router)
    except ImportError:
        logger.debug("projects router not yet available")

    try:
        from etelemetry_server.routes.dashboard import router as dashboard_router

        app.include_router(dashboard_router)
    except ImportError:
        logger.debug("dashboard router not yet available")

    # Disable uvicorn default access log to prevent IP logging
    logging.getLogger("uvicorn.access").disabled = True

    return app
