"""SomaCare API process. The Python package name stays turnwise."""

from __future__ import annotations

import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
for entry in (BACKEND, REPO / "ml", REPO):
    if entry.is_dir() and str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from turnwise.api import router
from turnwise.clock import clock_enabled, interval_seconds, tick
from turnwise.db import init_engine
from turnwise.models import Base
from turnwise.seed import seed_if_empty
from turnwise.settings import setting

# Explicit origins. A wildcard cannot be combined with credentials.
_DEFAULT_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "https://vercel.app",
)
# Preview hosts: https://*.vercel.app, Replit, and repl.co.
_ORIGIN_REGEX = r"https://.*\.(vercel\.app|replit\.app|repl\.co|replit\.dev)"


def _cors_origins() -> list[str]:
    origins = list(_DEFAULT_ORIGINS)
    extra = setting("CORS_ORIGINS", "") or ""
    for item in extra.split(","):
        item = item.strip().rstrip("/")
        if item and item not in origins:
            origins.append(item)
    return origins


def _cors_origin_regex() -> str:
    return setting("CORS_ORIGIN_REGEX", _ORIGIN_REGEX) or _ORIGIN_REGEX


def _alias_under_api(app: FastAPI) -> None:
    """Serve the same routes at /api so one origin can proxy /api/* here.

    This Starlette build keeps included routes on the router object, so the
    copy is taken from that router rather than the flattened app route list.
    """
    for route in list(router.routes):
        if not isinstance(route, APIRoute):
            continue
        if route.path.startswith("/api"):
            continue
        methods = [method for method in (route.methods or []) if method not in {"HEAD", "OPTIONS"}]
        app.add_api_route(
            "/api" + route.path,
            route.endpoint,
            methods=methods,
            name=f"api_{route.name}",
            operation_id=f"api_{route.name}",
            include_in_schema=True,
        )


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    stop = threading.Event()
    thread: threading.Thread | None = None
    if clock_enabled():

        def _loop() -> None:
            while not stop.wait(interval_seconds()):
                try:
                    tick()
                except Exception:
                    # A failed pass leaves last_tick_at where it was.
                    continue

        thread = threading.Thread(target=_loop, name="somacare-care-clock", daemon=True)
        thread.start()
    try:
        yield
    finally:
        stop.set()
        if thread is not None:
            thread.join(timeout=1)


def create_app() -> FastAPI:
    init_engine()
    from turnwise.db import ENGINE, SessionLocal

    Base.metadata.create_all(ENGINE)
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()

    app = FastAPI(
        title="SomaCare",
        version="0.1.0",
        lifespan=_lifespan,
        description=(
            "Care engine and API. Position, risk, scheduling and alerts are "
            "rules or trained models. Language models are not used for care decisions. "
            "Run with one worker so the care clock is not duplicated."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_origin_regex=_cors_origin_regex(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    _alias_under_api(app)
    return app


app = create_app()
