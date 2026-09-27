# TurnWise

Camera-verified turning and continence rounds. Nurses set every limit. CNAs log nothing for routine care. The care engine is rules and statistical models. It does not call a language model to score, schedule, or alert.

## Run it locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=backend:ml:.
uvicorn turnwise.main:app --reload --app-dir backend
```

The API seeds Harbor House: one unit, 10 rooms, 10 residents. Interactive docs are at `http://localhost:8000/docs`.

CNA app (port 3000) and nurse app (port 3001):

```bash
cd apps/cna && npm install && npm run dev
cd apps/nurse && npm install && npm run dev
```

Set `NEXT_PUBLIC_API_URL` if the API is not on `http://localhost:8000`.

### Demo sign-in

| Person | Role | PIN | Language |
| --- | --- | --- | --- |
| Maria Santos | CNA | 2468 | Spanish |
| Joy Reyes | CNA | 1357 | Tagalog |
| Devon Brooks | CNA | 8024 | English |
| Grace Adeyemi | Charge nurse | 5913 | English |
| Sam Patel | Nurse | 4470 | English |

Maria is assigned to the hall. Elena Alvarez is already inside her turn window, with a how-to card. Sam has a draft night limit for Mei Lin. Devon is not assigned, so the API refuses him Elena's card.

Edge token for `POST /events`: `edge-demo-token` (override with `TURNWISE_EDGE_TOKEN`).

A scripted posture sequence, with no camera and no frames written:

```bash
PYTHONPATH=backend:. python -m edge.demo --source scripted
```

## Tests

```bash
PYTHONPATH=backend:ml:. pytest
```

The continence test refits a small hazard model and takes a few seconds. The 14-day hall replay uses the real budget, limits, and alert budget.

## Docker

`docker compose up --build` starts Postgres (schema from `backend/migrations/001_initial.sql`), the API, and both apps. Postgres is optional for local development; the default database is SQLite under `var/`.

## What is deliberately not here

- SLP, MIMIC-IV, and PIID. See `docs/data_licenses.md`. Position events are labeled `position-v0.0.0-rules` until a model passes the cover and infrared gates.
- Any language-model call. Preference drafts are keyword rules and stay unapproved until a nurse accepts them.
- Video. Frames are dropped in memory. Skin uploads are encrypted under `var/skin/`, which is gitignored, and flagged `shown_to_staff = false`.

Spanish and Tagalog copy still needs review by native-speaking CNAs before a pilot.
