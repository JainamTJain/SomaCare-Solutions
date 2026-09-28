# somacare_ml findings (read first)

Plain Python. No LLM calls, no network, no API keys. Install: pip install -e ".[test]" then pytest (about a minute). The original pipeline suite is 31 tests. `tests/test_night_sim.py` checks the fictional six-bed night on top of that.

## What is proven and what is not
- Proven by unit tests and simulation: turn confirmation, the continence hazard model (gradient checked, simulator gates), patterns, the safety simulation, the recorded-test harness, the recording and frame-extraction tools.
- NOT proven: the position classifier has only run on SYNTHETIC images. It has never seen a real camera or a real person. Never quote a synthetic number as evidence.

## Findings from testing that shape the build
1. The dangerous error is a false confirmed turn (the system thinks a turn happened that did not). A missed turn only causes an extra alert.
2. A hard human-visit cap equal to limit plus tolerance (default 150 min for a 120 min limit) removes those failures. A 240 min cap does not. The tight cap gives back most visit savings, so early value is prioritization, alerts by exception and automatic records, not skipped visits.
3. Trusting camera-confirmed turns to shorten visits is only about as safe as paper below roughly 0.005 false confirmed turns per resident-hour. Showing that with zero events takes about 600 hours of footage (about 1,500 hours for 0.002). A short clip cannot prove a low rate: recorded_test.poisson_upper_95 gives the honest bound.
4. The continence model needs about 500 resident-days. At 100 resident-days two of three seeds passed the gates, at 300 the margin was thin (one run failed calibration at 0.061), at 500 all passed. Until then follow the nurse's schedule (model.learning is True).
5. After-meal patterns cannot be told apart from time-of-day patterns when meals are at fixed times. patterns.detect returns a 'confounded' note instead of a false finding.
6. Simulator results (well specified truth): calibration error 0.012 (gate under 0.05); voids handled within 60 minutes 36.9 percent fixed schedule versus 46.7 percent model schedule at the same visit count (26.7 percent relative, gate at least 20). With a truth the model cannot represent exactly: 0.019 and 24.9 percent.
7. MediaPipe's older mp.solutions pose API is gone in current versions. position/keypoints.py is optional, needs a downloaded pose_landmarker .task file, and is untested on real overhead poses.

## Data to collect
Overhead recordings of at least six consenting volunteers: five positions (back, left, right, sitting, out_of_bed) under each cover (none, sheet, blanket), plus a few continuous sessions of held-out people with a ground-truth csv (ts_s,label,cover,person). Use tools/record_and_label.py (press e first with an empty bed). Left and right mean the SUBJECT's left and right. Never commit images.

## Integration points
- TurnDetector.update(ts, label, confidence, persons) returns Events. backend_events.to_backend_event converts them to the POST /events contract. An 'uncertain' event is a status, not a care event.
- ContinenceModel.fit(observations), next_check_bin(...). Follow the nurse's schedule while model.learning is True.
- patterns.detect(change_minutes, meal_minutes). Show the text as written. It never changes a plan.
- All constants live in config.py. Clinician approval is needed for any limit or threshold. In pilot mode nothing may loosen a limit.

There is no `docs/STAGE1_TEST_REPORT.md`. That file waits on real recordings. Nothing in `reports/` is a measurement from a home or a real camera.
