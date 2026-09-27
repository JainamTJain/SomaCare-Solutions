"""Scope-specific consent. The words are the config file, filled in, never rewritten.

Camera position, a skin crop, and a continence prediction each require their
own signed record. A missing signature is an explicit schedule fallback.
Demo seed signatures are labeled demo-seed. They are not a power of attorney.
"""

from __future__ import annotations

from datetime import datetime, timezone

import yaml
from sqlalchemy.orm import Session

from turnwise.models import ConsentRecord, PoaContact, Resident
from turnwise.paths import BACKEND_ROOT

FORMS_PATH = BACKEND_ROOT / "config" / "consent_forms.yaml"
SCOPES = ("position_monitoring", "skin_capture", "continence_tracking")
SCHEDULE_LABEL = "monitored by schedule, not camera"


def form_book() -> dict:
    with FORMS_PATH.open() as handle:
        book = yaml.safe_load(handle)
    if set(book["forms"]) != set(SCOPES):
        raise RuntimeError("consent form file is missing a scope")
    return book


def fill_form(scope: str, resident_name: str, book: dict | None = None) -> str:
    book = book or form_book()
    if scope not in SCOPES:
        raise ValueError(f"unknown consent scope {scope}")
    template = book["forms"][scope].strip()
    text = (
        template.replace("{resident_name}", resident_name)
        .replace("{facility_name}", str(book["facility_name"]))
        .replace("{facility_contact}", str(book["facility_contact"]))
    )
    if "{" in text or "}" in text:
        raise RuntimeError("consent template left an unfilled placeholder")
    return text


def form_version() -> int:
    return int(form_book()["version"])


def latest_signed(db: Session, resident_id: str, scope: str) -> ConsentRecord | None:
    return (
        db.query(ConsentRecord)
        .filter(
            ConsentRecord.resident_id == resident_id,
            ConsentRecord.scope == scope,
            ConsentRecord.status == "signed",
            ConsentRecord.revoked_at.is_(None),
        )
        .order_by(ConsentRecord.signed_at.desc())
        .first()
    )


def has_signed(db: Session, resident_id: str, scope: str) -> bool:
    return latest_signed(db, resident_id, scope) is not None


def monitoring_state(db: Session, resident_id: str) -> dict:
    if has_signed(db, resident_id, "position_monitoring"):
        return {"mode": "camera", "reason": None, "label": None}
    return {"mode": "schedule", "reason": "consent", "label": SCHEDULE_LABEL}


def withhold_camera_fields(row: dict) -> dict:
    """Replace camera-derived numbers with the schedule fallback. Do not leave them blank."""
    row["monitoring"] = {"mode": "schedule", "reason": "consent", "label": SCHEDULE_LABEL}
    row["position"] = None
    row["last_known"] = None
    row["confidence"] = None
    row["confidence_pct"] = None
    row["uncertainty_pct"] = None
    row["areas"] = None
    row["worst_area"] = None
    row["worst_ratio"] = None
    row["inside_nurse_limit"] = None
    row["camera_online"] = None
    row["camera_spectrum"] = None
    row["model_version"] = None
    row["settled"] = None
    row["persons_in_zone"] = None
    row["visual_check"] = {
        "would_verify": False,
        "withheld": "consent",
        "blocked_by": ["consent"],
        "confidence_pct": None,
        "uncertainty_pct": None,
        "gate_pct": None,
    }
    return row


def withhold_continence_prediction(block: dict) -> dict:
    return {
        "wet_probability": None,
        "threshold": block.get("threshold"),
        "above_threshold": False,
        "learning": False,
        "reason_code": None,
        "withheld": "consent",
    }


def simple_pdf(text: str) -> bytes:
    """One-page PDF of the exact form. No external library and no extra wording."""
    lines = text.replace("\r", "").split("\n")
    wrapped: list[str] = []
    for line in lines:
        chunk = line.strip()
        while len(chunk) > 90:
            wrapped.append(chunk[:90])
            chunk = chunk[90:]
        wrapped.append(chunk)
    wrapped = wrapped[:48]
    commands = ["BT", "/F1 10 Tf", "48 760 Td", "14 TL"]
    for line in wrapped:
        safe = line.encode("latin-1", errors="replace").decode("latin-1")
        safe = safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands.append(f"({safe}) '")
    commands.append("ET")
    stream = ("\n".join(commands) + "\n").encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{number} 0 obj\n".encode())
        out.extend(body)
        out.extend(b"\nendobj\n")
    xref = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode())
    out.extend(
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(out)


def request_consent(db: Session, *, resident: Resident, scope: str, staff_id: str, now: datetime) -> ConsentRecord:
    if scope not in SCOPES:
        raise ValueError(f"unknown consent scope {scope}")
    row = ConsentRecord(
        resident_id=resident.id,
        scope=scope,
        status="requested",
        explanation_shown=fill_form(scope, resident.preferred_name),
        form_version=form_version(),
        requested_by=staff_id,
        requested_at=now,
    )
    db.add(row)
    db.flush()
    return row


def send_consent(db: Session, row: ConsentRecord, *, now: datetime, outbound: bool) -> dict:
    if row.status in {"signed", "declined", "revoked"}:
        raise ValueError(f"cannot send a {row.status} consent")
    row.status = "sent"
    row.sent_at = now
    if outbound:
        row.sent_to = "outbound_disabled_use_print"
    else:
        row.sent_to = "in_person"
    db.flush()
    return {"id": row.id, "status": row.status, "sent_to": row.sent_to, "pdf": True}


def sign_consent(
    db: Session,
    row: ConsentRecord,
    *,
    signer_name: str,
    relationship: str,
    now: datetime,
) -> ConsentRecord:
    if row.status not in {"requested", "sent"}:
        raise ValueError(f"cannot sign a {row.status} consent")
    name = signer_name.strip()
    if not name:
        raise ValueError("signer name is required")
    relation = relationship.strip() or "resident"
    db.add(
        PoaContact(
            resident_id=row.resident_id,
            full_name=name,
            relationship=relation,
            is_primary=True,
        )
    )
    row.status = "signed"
    row.signed_at = now
    row.signature_ref = name
    db.flush()
    return row


def revoke_consent(db: Session, row: ConsentRecord, *, reason: str, now: datetime) -> ConsentRecord:
    if row.status != "signed":
        raise ValueError("only a signed consent can be revoked")
    row.status = "revoked"
    row.revoked_at = now
    row.revoked_reason = reason.strip() or "revoked"
    db.flush()
    return row


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
