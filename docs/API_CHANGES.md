# API changes

Newest first. Every path below is also served with an `/api` prefix (`/health` and `/api/health` are the same handler). The contract file is `docs/openapi.json`. Regenerate it with `python scripts/export_openapi.py` in the same commit as a path change.

The Python package name remains `turnwise`. User-facing text says SomaCare.

## 2026-09-28

The care clock runs inside the API process every 30 seconds (`care_clock_s`). It recomputes budgets from stored timestamps, opens a turn alert inside the lead window, resends at 5 minutes, and escalates at 20. A second pass does not open a second alert for the same open turn. Run one worker. `SOMACARE_CARE_CLOCK=0` leaves the loop off. Tests call the same function with a moved clock, so the suite does not sleep for three minutes.

- `GET /config` returns `demoMode`, `facilityName`, and `logoUrl` from `DEMO_MODE`, `FACILITY_NAME`, and `LOGO_URL` (or `SOMACARE_FACILITY_NAME` and `SOMACARE_LOGO_URL`). No login.
- `GET /health` adds `last_tick_at` and `last_tick_duration_ms`. The older fields are unchanged.
- `GET /auth/roster` includes `pin` only when demo mode is on, and only for the seven demo profiles. Otherwise the field is absent.
- `POST /auth/login` still returns a bearer token. It also sets `somacare_session` as an httpOnly, SameSite=Lax cookie for 12 hours. A request may use the cookie when the Authorization header is absent. Five wrong PINs still lock the profile for 15 minutes.
- `GET /stream` is server-sent events. Each `update` event is the caller's residents and their open alerts. A caregiver sees the assignment. A nurse, charge nurse, engineer, director, or admin sees the hall. `?once=true` sends one event and closes. The position is omitted when position consent is not signed.
- `POST /leads` is public. Body: `name`, `email`, `organization`, `kind` (`pilot`, `investor`, `partner`, `other`), `message`. `GET /leads` is director or admin.
- `GET /me/tours` and `POST /me/tours` store which walkthrough keys this person has seen. A second post for the same key does not add a row.
- `POST /nurse/schedules` writes a new draft version (`windows` of `fixed` or `blackout`, each with `label`, `start`, `end` as `HH:MM`, plus a `reason`). `POST /nurse/schedules/{template_id}/approve` approves that version and does not rewrite older versions. `GET /nurse/schedules/{resident_id}` lists versions, newest first. The shift adds a fixed check while its window contains now, and hides a non-urgent `check` during a blackout. An escalated alert is not hidden.
- `GET /director/load` returns residents per caregiver on the current shift and `over` when the count is above `caregiver_ratio` in config. The flag does not change the schedule.
- `GET /residents/{resident_id}/timeline` returns the merged feed from the full picture, including meals and medication. An empty source says it is empty.
- `POST /residents/{resident_id}/meals` records `meal_type` (`breakfast`, `lunch`, `dinner`, `snack`), `items_text`, `percent_eaten`, and `fluid_intake_ml`.
- `GET /residents/{resident_id}/full-picture` timeline sources now include `meals` and `medications`.
- `GET /engineer/board` camera rows add `origin` (`somacare` or `existing`), `consent_state` (`signed`, `missing`, `no_resident`), and `consent_warning` when an existing camera has no signed position consent.
- `GET /me/shift.ics` downloads `somacare-shift.ics`.
- Consent templates are version 2. New requests store SomaCare wording and `form_version: 2`. A record already stored at version 1 keeps that text and version.
- `SOMACARE_*` environment names are preferred. `TURNWISE_*` still works. `DATABASE_URL` is used when neither database variable is set, including a Postgres URL. Tests keep using SQLite.

## Backfill, as the API stood before this contract

These shipped earlier. The date on this heading is the day they were written into the contract, not the day each one first appeared.

- `GET /health`. Process up, pilot mode, language-model flags (both off), Gate 1 `not_run`, resident data marked demo only.
- `GET /auth/roster`. Id, name, role, and language for each staff profile.
- `POST /auth/login`. Staff id and PIN. Returns a bearer token. Lockout after five failures.
- `GET /consent`. Resident by scope, with status and the stored explanation.
- `POST /consent/request`. Body `resident_id`, `scope` (`position_monitoring`, `skin_capture`, `continence_tracking`). Stores the exact template text.
- `POST /consent/{record_id}/send`. Marks the request sent. Outbound email is off. The response includes a printable form.
- `POST /consent/{record_id}/sign`. Body `signer_name`, `relationship`.
- `POST /consent/{record_id}/revoke`. Body `reason`.
- `GET /consent/{record_id}/form`. The stored words, as HTML or a small PDF.
- `GET /setup/status`. Live counts for facility, rooms, residents, staff, and consent.
- `POST /events`. Edge token. Position and related events. Duplicate device, timestamp, and kind are ignored.
- `POST /events/heartbeat`. Edge token. Device seen, no image stored.
- `POST /ingest/records`. A records file. The same checksum is not imported twice.
- `GET /export/care`. Care rows for the caller.
- `GET /engineer/board`. Per-resident position, ratios, and camera rows. Camera-derived fields are withheld without signed position consent. The response says monitored by schedule.
- `GET /director/board`. Hours estimate with the coefficients, residents inside the nurse limit, ulcers prevented left null.
- `GET /me/shift`. Ranked visits, why the first resident is ahead, minutes not walked, chart lines.
- `GET /me/shift.ics`. The same shift as a calendar file.
- `GET /residents/{resident_id}/card`. How-to card, preferences, vitals, diet pattern. Camera fields follow consent.
- `GET /residents/{resident_id}/full-picture`. Risk factors, Braden, medications, continence features, timeline. Empty sources are marked empty.
- `GET /residents/{resident_id}/history`. Recent events for the resident.
- `GET /residents/{resident_id}/continence`. Wetness view, or the schedule fallback when continence consent is missing.
- `POST /alerts/{alert_id}/accept`. The assigned caregiver accepts.
- `POST /alerts/{alert_id}/pass`. Hands the alert to a teammate.
- `POST /alerts/{alert_id}/confirm`. Records the turn and resolves the open alert.
- `POST /help`. A caregiver asks for a second person.
- `POST /handoff/notes` and `GET /handoff/notes`. Shift notes.
- `GET /nurse/residents`. The hall list for a nurse.
- `GET /nurse/plans/pending` and `POST /nurse/plans/{plan_id}/approve`. Approval stores a reason. Pilot mode cannot loosen a limit.
- `POST /nurse/preferences/extract`. Keyword draft only. It is not approved by itself.
- `GET /nurse/preferences/pending` and `POST /nurse/preferences/{preference_id}/approve`.
- `POST /overrides` and `GET /nurse/overrides`. A nurse records why a limit was not followed.
- `POST /skin/captures`. Encrypted crop. `shown_to_staff` stays false. Requires signed skin consent.
- `POST /skin/assessments`. A nurse's own finding. Not a model label.
- `GET /stream/unit/{unit_id}` is a websocket hello. The server-sent `/stream` above is the live path for the single-origin app. The websocket is unchanged.
