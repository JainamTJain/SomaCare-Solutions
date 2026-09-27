# Gate 1 — blanket occlusion

Near-infrared from a consumer baby monitor is reflected light. A blanket is opaque to it in the same way it is opaque to visible light. A shoulder-hip rule has nothing to key on once a resident is covered, which is the normal night state. Gate 1 exists to measure that, including the dangerous case: a confident label that is wrong.

No trial in this repository was filmed. `GET /health` reports `gate1: not_run`. The scorer in `backend/turnwise/engine/gate1.py` does not read a camera. Feeding it an empty list returns `not_run`. Feeding it synthetic rows is how the decision rule is tested. A synthetic pass is not a hardware result. `hardware_hours` on the live status is 0.

## What to record

One rig. The camera already in the plan (Tapo C210 class, or the cheapest infrared baby monitor on hand). One person lying on a bed, in three conditions, with the truth written down before the frame is scored:

| Cover | What the camera should be allowed to claim today |
| --- | --- |
| `none` | A lab path only. High confidence can reset a timer. Gate 1 has not passed, so the event is stored as `per_side_unvalidated`. |
| `sheet` | Does not reset a timer. |
| `blanket` | Does not reset a timer. |

For every trial store the cover, the true side, the predicted side or none, the confidence, and the fusion label (`uncertain`, `likely`, or `confirmed`). Keep the three covers in separate tallies. Do not average them into one percentage.

## What counts as a failure

`score_trials` uses these decision lines. They are the experiment's rules, not measured performance.

- **False confirmed.** Fusion would reset the timer (`likely` or `confirmed`), confidence is at least 0.7, and the predicted side is not the truth. Rate above 0.02 on any cover fails the gate. This is the unsafe outcome: a missed reposition recorded as done. Silence (`uncertain`) is not this failure.
- **Cliff.** Agreement on `blanket` is at least 0.15 below agreement on `none`. Agreement counts only labels that would reset the timer and match the truth, divided by every trial in that cover. A smooth 90 / 85 / 80 story is not the hypothesis under test.
- **No per-side claim.** A cover whose agreement is under 0.80 fails that claim even if every miss was `uncertain`. Going silent under a blanket is a safe engine result and a failed sensing claim.

A fail sets `architecture` to `movement_stillness_only`: no per-side pressure budget from the camera. This repository does not contain a bed sensor. The narrowed claim still has to be validated on its own hardware before anyone ships it.

A pass requires all three covers scored, no false-confirmed breach, no cliff, and agreement at least 0.80 on each cover. The live product does not read that as permission. The live status stays `not_run` until a real labeled set is committed with the raw counts. Do not flip the status from a demo.

## What the running system does now

Camera and vision events with cover `sheet`, `blanket`, or `unknown` are stored and marked `fusion: uncertain`, `fusion_reason: cover_unvalidated`, `claim: withheld`. They do not move the pressure clock and do not resolve an open turn. Cover `none` can still reset, and the event is marked `per_side_unvalidated` and `gate1: not_run`. A witnessed turn with no camera source is unchanged: that path is a person recording a turn, not the camera.
