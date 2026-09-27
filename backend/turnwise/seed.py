"""One unit, ten rooms, ten residents, and a shift a CNA can open immediately."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from turnwise.auth import hash_pin
from turnwise.engine.budget import ALL_AREAS
from turnwise.models import (
    Alert,
    Assignment,
    Event,
    BradenAssessment,
    Facility,
    Plan,
    Preference,
    Resident,
    ResidentState,
    RiskFactor,
    Room,
    Shift,
    Staff,
    StaffCredential,
    Task,
    Unit,
)

NOW = datetime.now(timezone.utc)

RESIDENTS = [
    {
        "name": "Elena Alvarez",
        "lang": "es",
        "room": "12",
        "braden": (3, 3, 2, 2, 3, 2),
        "factors": ["prior_injury"],
        "limit": 120,
        "sitting": 60,
        "night": 120,
        "two_person": True,
        "load_back": 108,
        "movements": 0.4,
        "last_change_h": 3.2,
        "threshold": 0.55,
        "mattress": "high_density_foam",
        "prefs": [
            ("turning", "pref.turn.side_preferred", {"side": "right"}, "Resident prefers to be positioned on her right side at night."),
            ("turning", "pref.turn.pillow_knees", {}, "Pillow between knees reduces discomfort."),
            ("turning", "pref.turn.float_heels", {}, "Float her heels."),
            ("turning", "pref.turn.two_person", {}, "Turn with 2 people."),
            ("turning", "pref.turn.avoid_area", {"area": "left_hip"}, "Left hip is tender: avoid lying on it."),
            ("comfort", "pref.comfort.say_name_first", {}, "Say her name before touching her."),
            ("comfort", "pref.comfort.light_off", {}, "Likes the light off."),
            ("continence", "pref.continence.usual_time", {"time": "2:00"}, "Usually needs a change around 2am."),
        ],
    },
    {
        "name": "James Okonkwo",
        "lang": "en",
        "room": "14",
        "braden": (4, 3, 3, 3, 3, 2),
        "factors": [],
        "limit": 120,
        "sitting": 60,
        "night": None,
        "two_person": False,
        "load_back": 40,
        "movements": 2.5,
        "last_change_h": 1.0,
        "threshold": 0.6,
        "mattress": "standard",
        "prefs": [
            ("turning", "pref.turn.side_preferred", {"side": "left"}, "Prefers his left side."),
            ("comfort", "pref.comfort.say_name_first", {}, "Tell him before you touch him."),
        ],
    },
    {
        "name": "Mei Lin",
        "lang": "en",
        "room": "16",
        "braden": (3, 3, 2, 2, 2, 2),
        "factors": ["diabetes"],
        "limit": 120,
        "sitting": 60,
        "night": 120,
        "two_person": False,
        "load_back": 70,
        "movements": 0.6,
        "last_change_h": 2.0,
        "threshold": 0.6,
        "mattress": "high_density_foam",
        "prefs": [
            ("turning", "pref.turn.float_heels", {}, "Float her heels."),
            ("turning", "pref.turn.pillow_knees", {}, "Pillow between her knees."),
        ],
        "draft": True,
    },
    {
        "name": "Rosa Delgado",
        "lang": "es",
        "room": "18",
        "braden": (3, 2, 2, 2, 3, 2),
        "factors": [],
        "limit": 120,
        "sitting": 45,
        "night": None,
        "two_person": False,
        "load_back": 20,
        "movements": 1.4,
        "last_change_h": 0.5,
        "threshold": 0.65,
        "mattress": "standard",
        "prefs": [
            ("comfort", "pref.comfort.light_off", {}, "Prefiere la luz apagada."),
            ("turning", "pref.turn.side_preferred", {"side": "right"}, "Prefiere su lado derecho."),
        ],
    },
    {
        "name": "Harold Bennett",
        "lang": "en",
        "room": "20",
        "braden": (4, 4, 3, 3, 3, 3),
        "factors": [],
        "limit": 180,
        "sitting": 90,
        "night": None,
        "two_person": False,
        "load_back": 15,
        "movements": 3.0,
        "last_change_h": 1.5,
        "threshold": 0.7,
        "mattress": "standard",
        "prefs": [
            ("comfort", "pref.comfort.say_name_first", {}, "Say his name first."),
        ],
        "settled_check": True,
    },
    {
        "name": "Leticia Ramos",
        "lang": "tl",
        "room": "22",
        "braden": (3, 3, 2, 2, 3, 2),
        "factors": [],
        "limit": 120,
        "sitting": 60,
        "night": 150,
        "two_person": False,
        "load_back": 55,
        "movements": 1.1,
        "last_change_h": 2.5,
        "threshold": 0.6,
        "mattress": "standard",
        "prefs": [
            ("turning", "pref.turn.side_preferred", {"side": "left"}, "Mas gusto niya ang kaliwang tagiliran."),
            ("turning", "pref.turn.pillow_knees", {}, "Unan sa pagitan ng mga tuhod."),
            ("comfort", "pref.comfort.say_name_first", {}, "Tawagin ang kanyang pangalan bago siya hawakan."),
        ],
    },
    {
        "name": "Samir Haddad",
        "lang": "en",
        "room": "24",
        "braden": (2, 3, 2, 2, 2, 1),
        "factors": ["vascular", "weight_loss"],
        "limit": 120,
        "sitting": 45,
        "night": 90,
        "two_person": True,
        "load_back": 50,
        "movements": 0.8,
        "last_change_h": 2.2,
        "threshold": 0.5,
        "mattress": "low_air_loss",
        "prefs": [
            ("turning", "pref.turn.two_person", {}, "Two people to turn him."),
            ("turning", "pref.turn.avoid_area", {"area": "right_hip"}, "Right hip is tender."),
            ("comfort", "pref.comfort.light_off", {}, "Likes the light off."),
        ],
    },
    {
        "name": "Patricia Nguyen",
        "lang": "en",
        "room": "26",
        "braden": (3, 3, 3, 2, 3, 2),
        "factors": [],
        "limit": 120,
        "sitting": 60,
        "night": None,
        "two_person": False,
        "load_back": 25,
        "movements": 1.8,
        "last_change_h": 0.8,
        "threshold": 0.6,
        "mattress": "standard",
        "prefs": [
            ("turning", "pref.turn.float_heels", {}, "Float her heels."),
        ],
    },
    {
        "name": "Carmen Ruiz",
        "lang": "es",
        "room": "28",
        "braden": (3, 3, 2, 2, 3, 2),
        "factors": [],
        "limit": 120,
        "sitting": 60,
        "night": None,
        "two_person": False,
        "load_back": 30,
        "movements": 1.2,
        "last_change_h": 1.2,
        "threshold": 0.6,
        "mattress": "standard",
        "prefs": [
            ("comfort", "pref.comfort.say_name_first", {}, "Diga su nombre antes de tocarla."),
        ],
        "camera_offline": True,
    },
    {
        "name": "Arthur Blake",
        "lang": "en",
        "room": "30",
        "braden": (2, 2, 1, 1, 2, 1),
        "factors": ["prior_injury"],
        "limit": 90,
        "sitting": 45,
        "night": 90,
        "two_person": True,
        "load_back": 78,
        "movements": 0.3,
        "last_change_h": 2.8,
        "threshold": 0.5,
        "mattress": "low_air_loss",
        "prefs": [
            ("turning", "pref.turn.two_person", {}, "Turn with 2 people."),
            ("turning", "pref.turn.side_preferred", {"side": "right"}, "Prefers his right side."),
            ("turning", "pref.turn.float_heels", {}, "Float his heels."),
            ("comfort", "pref.comfort.say_name_first", {}, "Say his name before touching him."),
        ],
    },
]

STAFF = [
    ("Maria Santos", "cna", "es", "2468"),
    ("Joy Reyes", "cna", "tl", "1357"),
    ("Devon Brooks", "cna", "en", "8024"),
    ("Grace Adeyemi", "charge_nurse", "en", "5913"),
    ("Sam Patel", "nurse", "en", "4470"),
]


def seed_if_empty(db: Session) -> None:
    if db.query(Facility).first():
        return
    now = datetime.now(timezone.utc)
    facility = Facility(name="Harbor House")
    db.add(facility)
    db.flush()
    unit = Unit(facility_id=facility.id, name="Night Hall")
    db.add(unit)
    db.flush()

    staff_rows = {}
    for name, role, lang, pin in STAFF:
        person = Staff(role=role, display_name=name, ui_language=lang)
        digest, salt = hash_pin(pin)
        db.add(person)
        db.flush()
        db.add(StaffCredential(staff_id=person.id, pin_hash=digest, pin_salt=salt))
        staff_rows[name] = person

    nurse = staff_rows["Sam Patel"]
    maria = staff_rows["Maria Santos"]
    shift = Shift(
        unit_id=unit.id,
        starts_at=now - timedelta(hours=2),
        ends_at=now + timedelta(hours=10),
    )
    db.add(shift)
    db.flush()

    for index, spec in enumerate(RESIDENTS):
        room = Room(
            unit_id=unit.id,
            label=spec["room"],
            camera_ref=f"demo-cam-{spec['room']}",
            camera_class="position_only",
            bed_zone={"polygon": [[0, 0], [1, 0], [1, 1], [0, 1]]},
            analysis_enabled=not spec.get("camera_offline", False),
            hallway_order=index,
        )
        db.add(room)
        db.flush()
        resident = Resident(
            room_id=room.id,
            preferred_name=spec["name"],
            language=spec["lang"],
            consent_position=True,
            consent_skin_capture=False,
            admitted_at=datetime(2026, 1, 15).date(),
        )
        db.add(resident)
        db.flush()
        sensory, moisture, activity, mobility, nutrition, friction = spec["braden"]
        db.add(
            BradenAssessment(
                resident_id=resident.id,
                assessed_at=now - timedelta(days=2),
                sensory=sensory,
                moisture=moisture,
                activity=activity,
                mobility=mobility,
                nutrition=nutrition,
                friction_shear=friction,
            )
        )
        for factor in spec["factors"]:
            db.add(
                RiskFactor(
                    resident_id=resident.id,
                    factor=factor,
                    source="record",
                    confirmed_by=nurse.id,
                    confirmed_at=now - timedelta(days=2),
                )
            )
        db.add(
            Plan(
                resident_id=resident.id,
                version=1,
                lying_limit_min=spec["limit"],
                sitting_limit_min=spec["sitting"],
                night_lying_limit_min=spec["night"],
                continence_threshold=spec["threshold"],
                mattress_type=spec["mattress"],
                two_person=spec["two_person"],
                approved_by=nurse.id,
                approved_at=now - timedelta(days=1),
                reason="Nurse-approved starting limit.",
                status="approved",
            )
        )
        if spec.get("draft"):
            db.add(
                Plan(
                    resident_id=resident.id,
                    version=2,
                    lying_limit_min=spec["limit"],
                    sitting_limit_min=spec["sitting"],
                    night_lying_limit_min=90,
                    continence_threshold=spec["threshold"],
                    mattress_type=spec["mattress"],
                    two_person=spec["two_person"],
                    status="draft",
                    reason="Night self-movement under 1 per hour over 3 nights.",
                    suggestion={
                        "rule": "extra_risk_steps.night_movements_per_hour<1",
                        "night_movements_per_hour": spec["movements"],
                        "proposed_night_lying_limit_min": 90,
                        "effect": "tighten",
                    },
                )
            )
        for category, code, params, excerpt in spec["prefs"]:
            db.add(
                Preference(
                    resident_id=resident.id,
                    category=category,
                    code=code,
                    params=params,
                    source_type="care_plan",
                    source_excerpt=excerpt,
                    source_date=datetime(2026, 3, 1).date(),
                    approved_by=nurse.id,
                    approved_at=now - timedelta(days=1),
                )
            )
        # One unapproved draft extracted from a note, for the nurse queue.
        if spec["name"] == "James Okonkwo":
            db.add(
                Preference(
                    resident_id=resident.id,
                    category="comfort",
                    code="pref.comfort.light_off",
                    params={},
                    source_type="nursing_note",
                    source_excerpt="He asked for the lights off after 9.",
                    source_date=datetime(2026, 9, 20).date(),
                )
            )
        load = {area: 0.0 for area in ALL_AREAS}
        for area in ("sacrum", "heels", "occiput"):
            load[area] = float(spec["load_back"])
        relief = {area: None for area in ALL_AREAS}
        db.add(
            ResidentState(
                resident_id=resident.id,
                load=load,
                relief_since=relief,
                last_known="back",
                position="back",
                last_ts=now,
                confidence=0.92,
                persons_in_zone=1,
                camera_online=not spec.get("camera_offline", False),
                settled=spec["load_back"] < 40,
                model_version="position-v0.0.0-rules",
                last_change_at=now - timedelta(hours=spec["last_change_h"]),
                moist_minutes_24h=0,
                night_movements_per_hour=spec["movements"],
            )
        )
        db.add(
            Assignment(shift_id=shift.id, resident_id=resident.id, staff_id=maria.id)
        )
        if spec.get("settled_check"):
            db.add(
                Task(
                    resident_id=resident.id,
                    kind="check",
                    due_at=now + timedelta(minutes=20),
                    window_min=30,
                    source="nurse_schedule",
                    status="open",
                    detail={"fixed_schedule": True},
                )
            )
        if spec.get("camera_offline"):
            db.add(
                Task(
                    resident_id=resident.id,
                    kind="check",
                    due_at=now + timedelta(minutes=45),
                    window_min=30,
                    source="nurse_schedule",
                    status="open",
                    detail={"fixed_schedule": True, "reason": "camera_offline"},
                )
            )

    db.flush()
    # Open the turn that Elena is already inside the lead window for.
    elena = db.query(Resident).filter(Resident.preferred_name == "Elena Alvarez").one()
    elena_state = db.get(ResidentState, elena.id)
    task = Task(
        resident_id=elena.id,
        kind="turn",
        due_at=now + timedelta(minutes=12),
        window_min=30,
        source="budget",
        status="open",
        priority=1.5,
        detail={"worst_area": "sacrum", "minutes_left": 12},
    )
    db.add(task)
    db.flush()
    db.add(
        Alert(
            task_id=task.id,
            staff_id=maria.id,
            created_at=now,
            rule="turn_due:minutes_left<=lead_min",
            inputs={
                "worst_area": "sacrum",
                "minutes_left": 12,
                "position": "back",
                "load_sacrum": elena_state.load["sacrum"],
                "pilot_mode": True,
            },
            plan_version=1,
            model_version="position-v0.0.0-rules",
            status="sent",
        )
    )
    for hours_ago, position in ((8, "left"), (5, "back"), (3, "right")):
        db.add(
            Event(
                room_id=elena.room_id,
                resident_id=elena.id,
                ts=now - timedelta(hours=hours_ago),
                kind="position",
                value={"position": position, "previous": "back", "persons_in_zone": 1},
                confidence=0.9,
                model_version="position-v0.0.0-rules",
            )
        )
    db.add(
        Event(
            room_id=elena.room_id,
            resident_id=elena.id,
            ts=now - timedelta(hours=5, minutes=10),
            kind="turn",
            value={"from": "left", "to": "back"},
            confidence=0.9,
            model_version="position-v0.0.0-rules",
        )
    )
    db.commit()
