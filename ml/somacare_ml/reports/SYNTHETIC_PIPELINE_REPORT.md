# Synthetic pipeline report

> Archived synthetic run. `docs/STAGE1_TEST_REPORT.md` does not exist yet. There are no real recordings.

**Read this first.** Every number below comes from simulated data or synthetic images. It proves the code runs and
the safety logic is sound. It is **not evidence** about real residents, real cameras or real accuracy. Real numbers
come from `docs/STAGE1_TEST_REPORT.md`, produced from real recordings.

## 1. Position classifier pipeline (synthetic overhead scenes, whole people held out)

People held out one at a time: 8. Temperature: 1.74. Calibration error: 0.072. Left-versus-right confusion: 4.5%.

| Cover | Frames | Correct over all frames | Correct when a claim is made | Unknown rate |
| --- | --- | --- | --- | --- |
| none | 800 | 45.8% | 98.4% | 53.5% |
| sheet | 800 | 37.9% | 96.5% | 60.7% |
| blanket | 800 | 5.9% | 65.3% | 91.0% |

Under a blanket the system reports unknown for most frames by design (a cover detector blocks the claim). The unknown rate in the other rows is high because this synthetic training set is tiny. The spec's gate is under 15 percent on real data, and how much recorded data it takes to get there is exactly what the first recordings will show.

## 2. Recorded-test harness on a synthetic 17-minute video of an unseen person

True position changes: 6. Detected: 6. Matched: 5 (tolerance 120 s). Precision 83.3%, recall 83.3%. Median latency 30 s.

False confirmed turns: 1 in 0.28 hours, which the harness reports as 3.5 per hour with a 95 percent upper bound of 19.7 per hour. **A short clip cannot prove a low rate**: showing a rate below 0.002 per hour with zero events needs about 1,500 hours of footage.

## 3. Safety simulation: is it safe when the position model is wrong?

24 residents, 14 days, limit 120 minutes, alert 15 minutes early, failure means true exposure over limit plus 30 minutes. Assumptions (all hypotheses to measure in the pilot): self-repositioning 0.25 per hour, 10 percent of visits missed.

| Scenario | Failures per resident-day | Longest true exposure (min) | Human visits per resident-day |
| --- | --- | --- | --- |
| paper: scheduled visits only, no camera | 0.0476 | 159.0 | 11.74 |
| camera, perfect model | 0.0595 | 177.0 | 9.77 |
| camera, misses 30% of self-repositions | 0.0655 | 185.0 | 10.46 |
| camera, 1 false confirm per 10 h, no cap | 1.0714 | 354.0 | 8.73 |
| camera, 1 false confirm per 10 h, cap 240 min | 0.8929 | 239.0 | 9.56 |
| camera, 1 false confirm per 10 h, cap = limit + tolerance | 0.0 | 149.0 | 11.32 |

Paper baseline: 0.0952 failures and 11.76 visits per resident-day (48 residents).

| False confirmed turns per hour | Failures per resident-day (trusting the camera, no cap) | Visits per resident-day |
| --- | --- | --- |
| 0.0 | 0.0536 | 9.68 |
| 0.001 | 0.0729 | 9.68 |
| 0.002 | 0.0804 | 9.67 |
| 0.005 | 0.1012 | 9.64 |
| 0.01 | 0.1592 | 9.59 |

**What this means.** A false confirmed turn (the system believes a turn happened that did not) is the dangerous error. Trusting the camera stays about as safe as paper only if false confirmed turns are around 0.005 per resident-hour or fewer, and proving that takes hundreds of hours of footage. Until then keep a hard visit cap at the limit plus the tolerance. That cap removes the failures, and it also gives back most of the visit savings. So early value comes from prioritization, alerts by exception and automatic records, not from skipped visits.

## 4. Continence model on the simulator

| Check | Well specified | Truth the model cannot represent exactly |
| --- | --- | --- |
| Calibration error (gate under 0.05) | 0.012 (pass) | 0.019 (pass) |
| Voids handled within 60 min, fixed schedule | 36.9% | 37.7% |
| Voids handled within 60 min, model schedule | 46.7% | 47.1% |
| Relative improvement (gate at least 20 percent) | 26.7% (pass) | 24.9% (pass) |
| Visits, fixed versus model | 3980 vs 4001 | 3980 vs 4000 |
| Learned night and diuretic effects have the right sign | True | True |

Data requirement: how many resident-days of history before the gates pass reliably (three random seeds each).

| Resident-days | Runs passing both gates | Calibration errors | Improvements |
| --- | --- | --- | --- |
| 100 | 2 of 3 | 0.038, 0.031, 0.041 | 0.25, 0.38, 0.11 |
| 300 | 3 of 3 | 0.047, 0.031, 0.049 | 0.38, 0.54, 0.51 |
| 500 | 3 of 3 | 0.022, 0.022, 0.028 | 0.43, 0.49, 0.46 |

Reading this: at 100 resident-days two of three runs passed. At 300 all three passed but calibration error sat close to the gate (0.03 to 0.05), and a separate 300 resident-day run in the test suite failed it at 0.061. At 500 every run passed with margin. Plan on about 500 resident-days, and until then run in learning mode and follow the nurse's schedule.

## 5. Patterns

A planted after-meal pattern was found: ['after_meal']. With meals at fixed times the module returns ['time_of_day', 'confounded'] (it says an after-meal pattern cannot be told apart from time of day). False-positive share on pure noise: 1.0%.
