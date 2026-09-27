# Model card: position, version 0 (rules)

Status: **not a trained model. Gate not met. Do not describe it as the SLP classifier.**

| | |
| --- | --- |
| Version | `position-v0.0.0-rules` |
| Method | Shoulder-hip line angle and shoulder-width / torso ratio |
| Data | None. SLP is not in this repository. |
| Split | Loader enforces a subject-wise 70/15/17 home split and refuses hospital or team ids in training. |
| Gate | Unmet. Targets remain 0.90 / 0.85 / 0.80 by cover, 0.85 on team infrared, ECE under 0.05. |
| Known failures | Side vs back depends on camera angle. Blankets, a second person in the foreground, and infrared night mode are untested. |
| Next step | Train Model A (ResNet-18 or EfficientNet-B0, recipe in `ml/datasets/slp.py`) after SLP access is recorded in `docs/data_licenses.md`. Horizontal flip swaps left and right. |
