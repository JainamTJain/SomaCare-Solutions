# Sorety

Camera-verified turning and continence rounds. Nurses set every limit. CNAs log nothing for routine care. The care engine is rules and statistical models. It does not call a language model to score, schedule, or alert.

The phone app is named Sorety. Each bed uses a cheap infrared baby monitor. One shared computer runs the shoulder-hip rule on those frames and throws the frames away. A side-of-body label under a blanket is not claimed: Gate 1 has not been run (`docs/plan_v3.md`, `docs/gate1_occlusion.md`). The shift can be dropped onto Google Calendar, and the summary shows minutes the CNA did not walk. How that sits on a real hall is in `docs/wiring.md`.

## Run it locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=backend:ml:.
cd backend && uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

The API seeds Harbor House: one unit, 10 rooms, 10 residents. Interactive docs are at `http://127.0.0.1:8000/docs`.

CNA app (port 3000, directory `frontend/` for Replit) and nurse app (port 3001):

```bash
cd frontend && npm install && npm run dev
cd apps/nurse && npm install && npm run dev
```

`frontend/config.js` sends development traffic to `http://127.0.0.1:8000`. A production build uses `NEXT_PUBLIC_API_URL`, or the placeholder `https://onrender.com` until you paste the live Render URL.

### Demo sign-in

| Person | Role | PIN | Language |
| --- | --- | --- | --- |
| Maria Santos | CNA | 2468 | Spanish |
| Joy Reyes | CNA | 1357 | Tagalog |
| Devon Brooks | CNA | 8024 | English |
| Grace Adeyemi | Charge nurse | 5913 | English |
| Sam Patel | Nurse | 4470 | English |
| Riley Chen | Engineer | 9130 | English |
| Helen Cho | Director | 6204 | English |

Maria is assigned to the hall. Elena Alvarez is already inside her turn window, with a how-to card. Sam has a draft night limit for Mei Lin. Devon is not assigned, so the API refuses him Elena's card. Riley opens the engineer board (live position, area scores, incontinence probability, visual-check uncertainty, and one row per infrared baby monitor). Helen opens the director board (hours saved, and pressure-ulcer prevention left unestimated).

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

`docker compose up --build` starts Postgres (schema from `backend/migrations/001_initial.sql`), the API, and both apps. Postgres is optional for local development; the default database is SQLite under `backend/var/`.

## Deploy

Render hosts the Python API. Replit or Vercel hosts `frontend/`.

1. On Render, New → Web Service, connect this repo. Root Directory: `backend`. Build command: `pip install -r requirements.txt`. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`. `render.yaml` records the same settings. Set `TURNWISE_SECRET`, `TURNWISE_EDGE_TOKEN`, and `TURNWISE_CORS_ORIGINS` to the live front-end origin (comma-separated if you have more than one).
2. Copy the service URL Render prints.
3. In Replit or Vercel, set `NEXT_PUBLIC_API_URL` to that URL and rebuild `frontend/`. Until you do, production builds call the placeholder `https://onrender.com` in `frontend/config.js`. Local `npm run dev` keeps using `http://127.0.0.1:8000`.
4. The API allows `http://localhost:3000`, `http://127.0.0.1:3000`, the nurse app on port 3001, `https://vercel.app`, and `https://*.vercel.app` / Replit hosts. Add any other origin with `TURNWISE_CORS_ORIGINS`.

## What is deliberately not here

- SLP, MIMIC-IV, and PIID. See `docs/data_licenses.md`. Position events are labeled `position-v0.0.0-rules` until a model passes the cover and infrared gates.
- Any language-model call. Preference drafts are keyword rules and stay unapproved until a nurse accepts them.
- Video. Frames are dropped in memory. Skin uploads are encrypted under `backend/var/skin/`, which is gitignored, and flagged `shown_to_staff = false`.

Spanish and Tagalog copy still needs review by native-speaking CNAs before a pilot.
