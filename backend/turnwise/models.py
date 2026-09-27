"""Clinical tables from the engineering spec, plus operational tables the
services need (budget snapshot, credentials, audit, help, handoff)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Facility(Base):
    __tablename__ = "facility"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(Text, nullable=False)


class Unit(Base):
    __tablename__ = "unit"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    facility_id: Mapped[str] = mapped_column(ForeignKey("facility.id"))
    name: Mapped[str] = mapped_column(Text)


class Room(Base):
    __tablename__ = "room"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    unit_id: Mapped[str] = mapped_column(ForeignKey("unit.id"))
    label: Mapped[str] = mapped_column(Text)
    camera_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    camera_class: Mapped[str] = mapped_column(String(32), default="position_only")
    bed_zone: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    analysis_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    hallway_order: Mapped[int] = mapped_column(Integer, default=0)


class Resident(Base):
    __tablename__ = "resident"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    room_id: Mapped[str] = mapped_column(ForeignKey("room.id"))
    preferred_name: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    consent_position: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_skin_capture: Mapped[bool] = mapped_column(Boolean, default=False)
    admitted_at: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    room: Mapped[Room] = relationship()


class Staff(Base):
    __tablename__ = "staff"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    role: Mapped[str] = mapped_column(String(32))
    display_name: Mapped[str] = mapped_column(Text)
    ui_language: Mapped[str] = mapped_column(String(8), default="en")


class StaffCredential(Base):
    __tablename__ = "staff_credential"
    staff_id: Mapped[str] = mapped_column(ForeignKey("staff.id"), primary_key=True)
    pin_hash: Mapped[str] = mapped_column(String(128))
    pin_salt: Mapped[str] = mapped_column(String(64))


class Shift(Base):
    __tablename__ = "shift"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    unit_id: Mapped[str] = mapped_column(ForeignKey("unit.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Assignment(Base):
    __tablename__ = "assignment"
    shift_id: Mapped[str] = mapped_column(ForeignKey("shift.id"), primary_key=True)
    resident_id: Mapped[str] = mapped_column(ForeignKey("resident.id"), primary_key=True)
    staff_id: Mapped[str] = mapped_column(ForeignKey("staff.id"))


class BradenAssessment(Base):
    __tablename__ = "braden_assessment"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    resident_id: Mapped[str] = mapped_column(ForeignKey("resident.id"))
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sensory: Mapped[int] = mapped_column(Integer)
    moisture: Mapped[int] = mapped_column(Integer)
    activity: Mapped[int] = mapped_column(Integer)
    mobility: Mapped[int] = mapped_column(Integer)
    nutrition: Mapped[int] = mapped_column(Integer)
    friction_shear: Mapped[int] = mapped_column(Integer)

    @property
    def total(self) -> int:
        return (
            self.sensory
            + self.moisture
            + self.activity
            + self.mobility
            + self.nutrition
            + self.friction_shear
        )


class RiskFactor(Base):
    __tablename__ = "risk_factor"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    resident_id: Mapped[str] = mapped_column(ForeignKey("resident.id"))
    factor: Mapped[str] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_by: Mapped[str | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Plan(Base):
    __tablename__ = "plan"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    resident_id: Mapped[str] = mapped_column(ForeignKey("resident.id"))
    version: Mapped[int] = mapped_column(Integer)
    lying_limit_min: Mapped[int] = mapped_column(Integer)
    sitting_limit_min: Mapped[int] = mapped_column(Integer)
    night_lying_limit_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    continence_threshold: Mapped[float] = mapped_column(Float, default=0.6)
    mattress_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    two_person: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    # Suggestion metadata. A model may propose a tighter limit; it is not active
    # until a nurse approves it, and pilot mode rejects a looser suggestion.
    suggestion: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Preference(Base):
    __tablename__ = "preference"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    resident_id: Mapped[str] = mapped_column(ForeignKey("resident.id"))
    category: Mapped[str] = mapped_column(String(32))
    code: Mapped[str | None] = mapped_column(Text, nullable=True)
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    text_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_es: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_tl: Mapped[str | None] = mapped_column(Text, nullable=True)
    translated_flags: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Event(Base):
    __tablename__ = "event"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[str | None] = mapped_column(ForeignKey("room.id"), nullable=True)
    resident_id: Mapped[str | None] = mapped_column(ForeignKey("resident.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(32))
    value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_version: Mapped[str | None] = mapped_column(Text, nullable=True)


class ContinenceObs(Base):
    __tablename__ = "continence_obs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resident_id: Mapped[str] = mapped_column(ForeignKey("resident.id"))
    kind: Mapped[str] = mapped_column(String(32))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    interval_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Task(Base):
    __tablename__ = "task"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    resident_id: Mapped[str] = mapped_column(ForeignKey("resident.id"))
    kind: Mapped[str] = mapped_column(String(32))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    merged_into: Mapped[str | None] = mapped_column(ForeignKey("task.id"), nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open")
    priority: Mapped[float] = mapped_column(Float, default=0)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Alert(Base):
    __tablename__ = "alert"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("task.id"), nullable=True)
    staff_id: Mapped[str | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    rule: Mapped[str] = mapped_column(Text)
    inputs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    plan_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="sent")
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    charge_notified: Mapped[bool] = mapped_column(Boolean, default=False)


class SkinCapture(Base):
    __tablename__ = "skin_capture"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    resident_id: Mapped[str] = mapped_column(ForeignKey("resident.id"))
    area: Mapped[str] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    source: Mapped[str] = mapped_column(String(16))
    image_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_flag: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    shown_to_staff: Mapped[bool] = mapped_column(Boolean, default=False)


class SkinAssessment(Base):
    __tablename__ = "skin_assessment"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    resident_id: Mapped[str] = mapped_column(ForeignKey("resident.id"))
    area: Mapped[str] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finding: Mapped[str] = mapped_column(String(32))
    warmth: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    firmness: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    pain: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    assessed_by: Mapped[str | None] = mapped_column(ForeignKey("staff.id"), nullable=True)


class Override(Base):
    __tablename__ = "override"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    target_type: Mapped[str] = mapped_column(Text)
    target_id: Mapped[str] = mapped_column(String(36))
    by_staff: Mapped[str | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ResidentState(Base):
    """Derived snapshot so the budget does not have to be replayed on every read."""

    __tablename__ = "resident_state"
    resident_id: Mapped[str] = mapped_column(ForeignKey("resident.id"), primary_key=True)
    load: Mapped[dict] = mapped_column(JSON)
    relief_since: Mapped[dict] = mapped_column(JSON)
    last_known: Mapped[str] = mapped_column(String(32), default="back")
    position: Mapped[str] = mapped_column(String(32), default="back")
    last_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float] = mapped_column(Float, default=0.9)
    persons_in_zone: Mapped[int] = mapped_column(Integer, default=1)
    camera_online: Mapped[bool] = mapped_column(Boolean, default=True)
    camera_spectrum: Mapped[str] = mapped_column(String(32), default="infrared")
    settled: Mapped[bool] = mapped_column(Boolean, default=True)
    model_version: Mapped[str] = mapped_column(Text, default="position-v0.0.0-rules")
    last_change_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    moist_minutes_24h: Mapped[float] = mapped_column(Float, default=0)
    night_movements_per_hour: Mapped[float | None] = mapped_column(Float, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    staff_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(Text)
    target_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class HelpRequest(Base):
    __tablename__ = "help_request"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    resident_id: Mapped[str] = mapped_column(ForeignKey("resident.id"))
    requester_id: Mapped[str] = mapped_column(ForeignKey("staff.id"))
    teammate_id: Mapped[str | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    eta_min: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = mapped_column(String(16), default="sent")


class HandoffNote(Base):
    __tablename__ = "handoff_note"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    staff_id: Mapped[str] = mapped_column(ForeignKey("staff.id"))
    shift_id: Mapped[str | None] = mapped_column(ForeignKey("shift.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    audio_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_status: Mapped[str] = mapped_column(String(32), default="pending_local_asr")
    text_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class MorningVital(Base):
    """The morning chart the facility already collects. Not re-entered by the CNA."""

    __tablename__ = "morning_vital"
    __table_args__ = (UniqueConstraint("resident_id", "recorded_on"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    resident_id: Mapped[str] = mapped_column(ForeignKey("resident.id"))
    recorded_on: Mapped[datetime] = mapped_column(Date)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    systolic: Mapped[int | None] = mapped_column(Integer, nullable=True)
    diastolic: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pulse: Mapped[int | None] = mapped_column(Integer, nullable=True)
    temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    spo2: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="morning_chart")


class IngestBatch(Base):
    __tablename__ = "ingest_batch"
    __table_args__ = (UniqueConstraint("source_name", "checksum"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_name: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
