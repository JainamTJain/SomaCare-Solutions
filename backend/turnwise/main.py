"""TurnWise API process."""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
for entry in (BACKEND, REPO / "ml", REPO):
    if entry.is_dir() and str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from turnwise.api import router
from turnwise.db import init_engine
from turnwise.models import Base
from turnwise.seed import seed_if_empty

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
    extra = os.environ.get("TURNWISE_CORS_ORIGINS", "")
    for item in extra.split(","):
        item = item.strip().rstrip("/")
        if item and item not in origins:
            origins.append(item)
    return origins


def _cors_origin_regex() -> str:
    return os.environ.get("TURNWISE_CORS_ORIGIN_REGEX", _ORIGIN_REGEX)


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
        title="TurnWise",
        version="0.1.0",
        description=(
            "Care engine and API. Position, risk, scheduling and alerts are "
            "rules or trained models. Language models are not used for care decisions."
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
    return app


app = create_app()
