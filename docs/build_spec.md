# TurnWise build spec (engineering)

This file is the ground-rule copy for the repository. The product behavior is the
27 Sep 2026 engineering spec: care decisions are rules or trained models, never
a language model.

## Ground rules

1. No generative model in position detection, movement, risk, continence, scheduling, or alerts.
2. A language model is allowed in only two optional places, both off by default: draft preference codes from a free-text note (a nurse must approve) and translation of free text that does not map to a code (labeled translated, original one tap away). The fallbacks are the keyword extractor and showing the original text.
3. No model is shown to staff until its acceptance gate passes.
4. Splits are by person. A participant cannot be in both train and test.
5. Nurses approve every limit. In pilot mode a multiplier above 1 raises `PilotModeError`.
6. Frames are processed in memory and discarded. Events are what leave the device.
7. Every alert stores the rule, inputs, plan version, and model version.
8. Dependencies stay on permissive licenses (Apache-2.0, MIT, BSD). No AGPL weights.

## What is implemented

- Care engine in `backend/turnwise/engine`: pressure budget, version-1 risk steps, scheduler, alerts, continence likelihood.
- API, seed (one unit, 10 rooms, 10 residents), CSV ingest/export, role checks, audit log.
- Edge version-0 position rules (shoulder-hip angle), smoothing, movement/presence/exit/bath rules. Model version `position-v0.0.0-rules`.
- SLP loader with the left/right flip swap and a 70/15/17 subject split. Training does not run without the dataset.
- Continence simulator with the calibration and schedule gates.
- 14-day, 24-resident facility replay.
- Skin quality rules. Captures are encrypted and stored with `shown_to_staff = false`.
- CNA app (English, Spanish, Tagalog) and nurse approval app.
- Constants in `backend/config/turnwise.yaml` (same file also at `config/turnwise.yaml`).

## Not claimed

- A position model trained on SLP. The night-mode and cover gates are unmet.
- MIMIC-IV risk model version 2. Version 1 rules are what the pilot runs.
- A skin classifier shown to staff.
- Clinical value of the continence model. The simulator only shows that the code can learn a known process.

Spanish and Tagalog strings follow the product examples and still need review by native-speaking CNAs before a real pilot.
