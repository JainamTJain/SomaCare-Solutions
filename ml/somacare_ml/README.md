# somacare_ml

Predictive analysis for SomaCare. Plain Python, no LLM calls, no network access, no API keys. Drop this folder into the
repo as `ml/somacare_ml/`, run `pip install -e ".[test]"`, then `pytest` (about a minute).

The live edge pipeline stays on `position-v0.0.0-rules`. This package does not replace it, and it does not loosen a care limit.

## What is here, and what has been proven

| Module | What it does | Proven how |
| --- | --- | --- |
| `turn.py` | Confirms position changes from noisy per-frame readings. Unsure readings never reset a timer. | Unit tests |
| `safety_sim.py` | Injects position-model errors and measures whether residents stay inside their limits. | Simulation, with a sweep that sets the false-confirm gate |
| `continence/` | Discrete-time hazard model of wetness, fitted by MAP with analytic gradients, with a simulator and the spec's gates. | Gradient check to 1e-6, simulator gates over several seeds, a misspecified-truth run |
| `patterns.py` | Time-of-day and after-meal patterns with sample sizes and p-values. Says so when meals are too regular to separate from time of day. | Planted-pattern and noise tests |
| `position/` | Overhead position classifier: mask and shape features, leave-one-person-out training, temperature calibration, a cover detector that returns `unknown` under a blanket. | Runs end to end on SYNTHETIC scenes only |
| `recorded_test.py` | The recorded ceiling-view test: accuracy by cover, turn precision and recall, false confirmed turns per hour with a 95 percent bound, latency. | Runs on a synthetic video |
| `tools/` | `record_and_label.py` (label frames with key presses), `extract_frames.py`, `run_live.py` (classifier plus turn detector, posts events to `/events`). | Logic tested without a camera |
| `night_sim.py` | One fictional night in a six-bed home. The `/simulate` page plays the same rules. | Qualitative checks in `tests/test_night_sim.py` |

**Nothing here has been tested on a real camera or a real person.** The position classifier's real accuracy comes from
your recordings. See `reports/SYNTHETIC_PIPELINE_REPORT.md` for the numbers that exist, all simulated.

## Data you must collect

* Position: overhead recordings of volunteers, with written consent. At least six people, all five positions, each cover
  condition (none, thin sheet, thick blanket), day and night mode. Use `tools/record_and_label.py`. Agree first that left
  and right mean the SUBJECT's left and right.
* Continence: the model runs in learning mode and follows the nurse's schedule until it has about 500 resident-days.
* False confirmed turns: proving a rate under 0.002 per resident-hour with zero events needs about 1,500 hours of footage.
  Until then the system keeps a hard human-visit cap at the limit plus tolerance (see `safety_sim.py`).

## Workflow

```
python -m somacare_ml.tools.record_and_label --source 0 --person p01 --out data/raw     # press e first, empty bed
python - <<'PY'
from somacare_ml.position.dataset import load_dataset, load_background
from somacare_ml.position.train import train_and_evaluate
import json
root = "data/raw"; ds = load_dataset(root); bg = load_background(root)
report, clf = train_and_evaluate(ds, bg); clf.save("models/position.joblib")
print(json.dumps(report, indent=1))
PY
python -m somacare_ml.tools.run_live --model models/position.joblib --source video.mp4 --post-url http://127.0.0.1:8000/events --token $SOMACARE_EDGE_TOKEN
```

`run_live` tags events `position-gbdt-v0.1`. That string is this optional classifier. The product's live model version remains `position-v0.0.0-rules` until real recordings exist and a clinician approves a change.

## Integration points

* `TurnDetector.update(ts, label, confidence, persons)` returns events. Convert with `backend_events.to_backend_event` to
  the backend's `POST /events` contract. `uncertain` is a status, not a care event.
* `ContinenceModel.fit(observations)` then `next_check_bin(...)` for the schedule. Turn a charted wet or dry check, a
  sensor alert or a bathroom trip into an `Observation`. Follow the nurse's schedule while `model.learning` is true.
* `patterns.detect(change_minutes, meal_minutes)` for the nurse's patterns page. Show the text as written.
* Every constant is in `config.py`. Limits and thresholds need nurse or clinician approval. In pilot mode nothing here may loosen a limit.

## Not here (tasks for the build)

A GPU trainer for a CNN on SLP, the thermal model, the skin classifier. Skin findings are not shown and do not drive care.
