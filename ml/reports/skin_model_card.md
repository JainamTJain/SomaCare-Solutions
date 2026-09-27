# Model card: skin, shadow mode

Status: **not shown to staff. `shown_to_staff` is forced false.**

Step 1 (rules, in `ml/skin/quality.py`): Laplacian sharpness, exposure, and a printed color card. A 3×3 least-squares matrix corrects color from the card. No hue jitter is used, because it would distort redness.

Step 2 is not trained. PIID is not in this repository. When it is, near-duplicates must be removed with perceptual hashing before any split, because patient ids may be missing. Healthy skin has to come from consented pilot photos. The stage output stays research-only. The nurse stages injuries.

Gate before any flag is shown: stage 2+ sensitivity at least 0.90, specificity at least 0.80, skin-tone sensitivity gap within 0.05, on pilot photos paired with a hands-on assessment.
