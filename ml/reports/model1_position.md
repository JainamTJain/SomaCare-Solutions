# Model 1 — position

Status: **not run**. The edge classifier is still `position-v0.0.0-rules`, the shoulder-hip rule.

SLP was not downloaded. The license is research-use and is requested from the Northeastern ACLab. This machine does not have the files, and this build does not train or export ONNX. `ml/position/train.py` exits if `--slp-root` is missing.

No team recording is on file. Gate 1 (no cover, sheet, blanket, including false confirmed labels) has not been filmed. See `docs/gate1_occlusion.md`.

| Gate | Result |
| --- | --- |
| Agreement, no cover | not run |
| Agreement, sheet | not run |
| Agreement, blanket | not run |
| Left/right confusion | not run |
| Calibration error | not run |
| Unknown rate | not run |
| Horizontal flip swaps left and right | unit-tested on the loader, not on a trained model |

A failed blanket gate would leave this rule in place. That is the current state, because the gate was not run, not because a model missed a number.
