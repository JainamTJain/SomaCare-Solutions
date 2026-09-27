"""Staff sessions and role checks. PINs are hashed; tokens are signed."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from turnwise.db import get_session
from turnwise.models import Staff, StaffCredential

TOKEN_MAX_AGE_S = 12 * 60 * 60


def _secret() -> str:
    return os.environ.get("TURNWISE_SECRET", "turnwise-dev-secret-change-me")


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_secret(), salt="turnwise-session")


def edge_token() -> str:
    return os.environ.get("TURNWISE_EDGE_TOKEN", "edge-demo-token")


def hash_pin(pin: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt.encode(), 120_000).hex()
    return digest, salt


def verify_pin(pin: str, credential: StaffCredential) -> bool:
    digest, _ = hash_pin(pin, credential.pin_salt)
    return hmac.compare_digest(digest, credential.pin_hash)


def issue_token(staff: Staff) -> str:
    return _serializer().dumps({"sub": staff.id, "role": staff.role})


@dataclass
class Principal:
    id: str
    role: str
    display_name: str
    ui_language: str
    is_edge: bool = False


def get_db(db: Session = Depends(get_session)) -> Session:
    return db


def get_principal(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_session),
) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if hmac.compare_digest(token, edge_token()):
        return Principal(id="edge", role="edge", display_name="Edge", ui_language="en", is_edge=True)
    try:
        data = _serializer().loads(token, max_age=TOKEN_MAX_AGE_S)
    except SignatureExpired as exc:
        raise HTTPException(status_code=401, detail="session expired") from exc
    except BadSignature as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc
    staff = db.get(Staff, data["sub"])
    if staff is None:
        raise HTTPException(status_code=401, detail="unknown staff")
    return Principal(
        id=staff.id,
        role=staff.role,
        display_name=staff.display_name,
        ui_language=staff.ui_language or "en",
    )


def require_roles(*roles: str):
    def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.role not in roles and not principal.is_edge:
            raise HTTPException(status_code=403, detail="role not allowed")
        return principal

    return _dep
