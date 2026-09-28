"""Convert detector events into the backend's POST /events contract.

{ room_id, resident_id, ts (ISO 8601 UTC), kind, value {position, previous, persons_in_zone}, confidence, model_version }
Kinds used: position, turn, movement (self reposition), camera_offline (feed gap). An 'uncertain' reading is not sent as a
care event: it is a status shown in the engineer view, and it never resets a timer."""
from datetime import datetime, timezone

KIND_MAP = {"turn": "turn", "self_reposition": "position", "position": "position", "feed_gap": "camera_offline"}


def to_backend_event(e, room_id, resident_id, model_version, persons_in_zone=1, epoch_offset=0.0):
    if e.kind not in KIND_MAP:
        return None
    ts = datetime.fromtimestamp(e.ts + epoch_offset, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    value = {"position": e.position, "previous": e.previous, "persons_in_zone": persons_in_zone}
    if e.kind == "self_reposition":
        value["self_repositioned"] = True
    if e.kind == "feed_gap":
        value = {"last_frame_at": ts}
    return {"room_id": room_id, "resident_id": resident_id, "ts": ts, "kind": KIND_MAP[e.kind], "value": value,
            "confidence": round(float(e.confidence), 3), "model_version": model_version}
