# Model card: pressure-injury risk, version 1

Status: **deterministic rules. This is what the pilot runs.**

Version 2 (MIMIC-IV) is not trained here and must not be deployed to residents even after it beats a Braden-only model. ICU patients are a different population. It may only inform these weights later.

## Bands

| Total | Band |
| --- | --- |
| ≤ 9 | very_high |
| 10–12 | high |
| 13–14 | moderate |
| 15–18 | mild |
| ≥ 19 | none |

## Extra steps, capped at 2

Prior injury; diabetes or vascular disease; weight loss or Braden nutrition ≤ 2; friction/shear = 1; night self-movements under 1 per hour when that measurement exists.

## Multipliers

`M_RISK = {0: 1.00, 1: 0.85, 2: 0.70}`. Moisture on sacrum or ischium multiplies by 0.85 after 120 moist minutes. Floor is 60 minutes unless a nurse records an override. Pilot mode rejects any multiplier above 1.

`eligible_for_3h` is a suggestion for the nurse. The engine does not lengthen a limit by itself.
