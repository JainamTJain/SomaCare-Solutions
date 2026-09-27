# Model 5 — visible injury

Status: **not trained**. PIID was not downloaded. Counsel has not scoped software-as-a-medical-device review. Skin findings are off the near-term roadmap.

There is no skin-camera device in the seed hall. A crop is not taken from the posture camera.

The only code path that decides whether a window could open is `turnwise.skinwindow.skin_window`. It stays closed unless skin consent is signed, a second person is present, the lights are on, and the body area is uncovered. There is no CNA photo button.

`shown_to_staff` is not set to true anywhere in this build.

| Gate | Result |
| --- | --- |
| Sensitivity | not run |
| Specificity | not run |
| Skin-tone gap | not run |
| Stage metrics | not run |

Do not show a skin finding to staff until those gates are measured on consented pilot data. No date is attached to that work.
