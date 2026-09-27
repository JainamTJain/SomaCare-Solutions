"""TurnWise API process."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT / "backend", ROOT / "ml", ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from turnwise.api import router
from turnwise.db import init_engine
from turnwise.models import Base
from turnwise.seed import seed_if_empty


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
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
