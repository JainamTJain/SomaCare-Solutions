"""The migration lists every clinical table from the spec."""

from pathlib import Path

TABLES = [
    "facility",
    "unit",
    "room",
    "resident",
    "staff",
    "shift",
    "assignment",
    "braden_assessment",
    "risk_factor",
    "medication_log",
    "plan",
    "preference",
    "event",
    "continence_obs",
    "task",
    "alert",
    "skin_capture",
    "skin_assessment",
    "override",
]


def test_migration_contains_clinical_tables():
    sql = (Path(__file__).resolve().parents[1] / "migrations" / "001_initial.sql").read_text()
    for name in TABLES:
        assert f"CREATE TABLE {name} " in sql
    assert "GENERATED ALWAYS AS" in sql
    assert "shown_to_staff BOOLEAN DEFAULT FALSE" in sql
