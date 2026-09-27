# Data licenses

Confirm each license at the time of access. Terms change. Do not commit dataset files to this repository.

| Dataset | Use | Access | Notes |
| --- | --- | --- | --- |
| SLP (Northeastern ACLab) | Position classifier | Request on the ACLab datasets page | Research-use terms. No near-infrared night images, so team recordings are required before a night-mode claim. |
| PmatData (PhysioNet) | Optional pressure-mat cross-check | Open access | Not camera data. Not used by the pilot path. |
| MIMIC-IV (PhysioNet) | Risk model version 2 | Credentialed access, human-subjects training, signed data use agreement | ICU patients are not long-term care residents. Do not deploy version 2 directly. Do not upload the data to a third-party service. |
| PIID | Visible-injury classifier | Confirm the current download and license before use | Injuries only. No healthy-skin negatives. Possible near-duplicates. Shadow mode until the pilot gate passes. |
| Team recordings | Position night mode, movement, presence, exits, baths | Written consent from volunteers | Keep separate from resident data. |
| Pilot data | Later models | Facility agreement, consent, and an IRB or quality-improvement determination | The most valuable data. Governed by the facility agreement. |

No dataset above is present in this repository. Training entry points refuse to start without a local path and a recorded license.
