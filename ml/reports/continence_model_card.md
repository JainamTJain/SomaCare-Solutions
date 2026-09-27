# Model card: continence hazard (simulator only)

Status: **the code learns a synthetic process. It says nothing about real residents.**

Model: discrete-time hazard, 30-minute bins,

`p = sigmoid(alpha + u_r + beta · x)`

with time since last event, time of day, night, meal, diuretic, and continence category. Charted wet and charted dry use the interval likelihoods in `backend/turnwise/engine/continence.py`.

## Gate (recomputed by `sim/tests/test_sim.py`, seed 7)

A local run of `evaluate(seed=7)` produced about:

- expected calibration error 0.022 (gate: under 0.05)
- relative improvement in voids followed by a change within 60 minutes, at the same visit count, about 0.25 (gate: at least 0.20)
- mean absolute error on beta about 0.14

Those figures move with the seed. The test is the gate, not this paragraph. Pilot value is unmet until wet findings fall without extra visits.
