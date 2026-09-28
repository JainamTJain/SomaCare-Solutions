# Stage 2 notes

Status of this drop: the modules are in `somacare_stage2/` and `tools/record_mlx.py`. Stage 1 files were not changed. `LABELS_VERIFIED` and `POSE_BLOCKS_VERIFIED` are still false. PMD, SLP, PIID, and PI-Net are not downloaded. Nothing here is wired into the care backend yet. Thresholds are placeholders until a nurse signs them off.

Ground rules, unchanged:

- No generative AI / LLM in any care decision, score, schedule, or alert. This rules out FT-ARM and any multimodal-LLM wound model.
- Every model is evaluated with subject-wise or group-wise splits. Never random frame or image splits.
- All thresholds live in config and are placeholders until a nurse signs them off.
- No video or thermal frames written to disk. ROI means and events only. Skin photos are the one exception, and only with the resident's skin-photo consent flag set.
- Outputs are "nurse review suggested" or "unsure", never a diagnosis. The skin check ships in silent/documentation mode for the pilot.

## Work order

After each task, run `pytest -q` and do not continue on red.

### Task 1: Position tracking on real data

1. Download PhysioNet PMD (open access, ODC-By): `wget -r -N -c -np https://physionet.org/files/pmd/1.0.0/`
2. Open `experiment-i/../experiment-info.docx`. Check `POSTURE_TO_CLASS` in `somacare_stage2/position/pmd.py` against it. Fix any mismatch, then set `LABELS_VERIFIED = True`.
3. Run `python -m somacare_stage2.position.train_eval <path>/pmd/1.0.0/experiment-i`. Save the output to `reports/position_pmd.json`. Report per-class recall and the worst subject.
4. Add a turn-level metric: collapse consecutive frames into posture segments, then count missed class changes and invented class changes per subject. The existing TurnDetector's hold-time confirmation should consume these per-frame probabilities. Wire `position/features.py` output into the existing position inference as an alternative feature extractor (`POSITION_FEATURES = "mask" | "grid"`).
5. SLP is request-only (`github.com/ostadabbas/SLP-Dataset-and-Code`). If files are present under `data/SLP`, use `position/slp.py`: downsample LWIR 160x120 to 24x32 with `to_mlx_like()` so training matches the MLX90640 we would deploy, verify the pose-index to class blocks against the SLP readme (set `POSE_BLOCKS_VERIFIED`), train with leave-one-subject-out, and report accuracy separately for uncover / thin sheet / blanket. If SLP is absent, skip and leave a TODO. Do not fake it. `test_slp_smoke` skips when `SLP_ROOT` is unset.
6. Backend: emit posture probabilities into the existing POST /events contract as `{type:"posture", bed_id, t, probs:{supine,left,right}, source:"grid"}`.

### Task 2: Thermal continence

1. Read `continence_thermal/sim.py` and `detect.py`. The detector is rule-based: pelvis-minus-chest differential, masks around turns and caregiver-present windows, per-segment baseline, one-sided CUSUM to "possible wet" (silent), then "likely wet" when the evaporative cooling drop appears.
2. Feed it the real turn times from the position pipeline and the second-person flag from the existing care-event detector. Emit `{type:"continence", level:"possible"|"likely", t, peak_rise}`.
3. Connect "likely" events to the existing continence MAP hazard model as observed voids, replacing manual logs where a sensor exists. Keep manual logs as the fallback and as ground truth.
4. Add `tools/replay_bench.py`: read a CSV from `tools/record_mlx.py`, run `detect()`, and print hits, misses, and false flags against the `v` markers. Tune only `DET` values in config, never code constants, and record the tuned values plus the CSV name in `reports/continence_bench.json`.
5. A replay of any bench CSV must reproduce identical events (determinism).

### Task 3: Bath-time skin check

1. Download PIID (`github.com/FU-MedicalAI/PIID`, Google Drive link in the README) into `data/PIID` with folders Stage-1 through Stage-4. Download PI-Net annotations and MIPI images from the Zenodo link in `github.com/clare304/PI-Net` into `data/PI-Net`.
2. Build the negative class: for each MIPI image and mask, call `skin.data.intact_skin_patches()`. Store under `data/skin_neg/`. These are intact skin from the same cameras, not internet stock photos.
3. Run `skin/train.py` (not run yet; fix what breaks). It groups near-duplicate photos before splitting, applies shades-of-gray colour constancy, uses no hue augmentation, temperature-calibrates, and abstains below `ABSTAIN_BELOW`. Then add model A (wound present vs intact) the same way, binary.
4. Report per-stage recall with Stage 1 first, abstain rate, and accuracy on answered cases. If any fold exceeds 90% four-class accuracy, treat it as leakage and investigate before continuing.
5. App flow (CNA app): during a bed bath, the CNA taps "Skin check", chooses a site (sacrum, L/R hip, L/R heel, other), takes a photo. Model A then B run on device or server. The result is shown to the nurse queue only, never to the CNA as a stage. Save the crop, site, time, model version, and output to the resident's skin record. Show the previous photo of the same site side by side. Change over time matters more than the stage label.
6. Add a banner in the nurse view when the resident's skin tone is darker (nurse-entered field): "Stage 1 redness is hard to see in photos on darker skin; check by touch and temperature."

Definition of done: all tests green, `reports/position_pmd.json` exists from real PMD data, `skin_report.json` exists from real PIID data, continence bench replay works on at least one CSV, and `README_STAGE2.md` lists every threshold that still needs nurse sign-off.

## Things to know before running it

Hardware for incontinence. "Via temperature" needs a sensor that measures temperature. The Tapo C210 sees 850 nm near-infrared, which is reflected light, not heat, so it cannot do this. Two workable options:

- Overhead MLX90640 (32x24 thermal). Non-contact, and it also helps position tracking through blankets, which is what SLP was built to show. At about 2 m height with the 55 degree lens each pixel covers roughly 6 to 7 cm, so the pelvis is a handful of pixels, fine for an ROI mean. Breakout boards are roughly $50 to $75, so it strains the under-$50-per-bed cap.
- Thermistor strip under the bed pad. A few dollars, closer to the patented approach, and a stronger signal because it sits right under the brief. It adds something to clean between residents.

Worth deciding which one the pilot uses. The detector only needs two temperature series, so it works for either.

What the continence numbers mean. On 80 simulated nights the detector caught 90% of voids with a median of about 33 seconds to the silent "possible" flag, and raised zero false flags across 80 dry nights that included turns and caregiver hands. Of the misses, over half happened during or just after a turn, where the mask deliberately looks away. These numbers come from a simulator whose constants are placeholders, so they prove the plumbing, not the product. The physics it models: a patent on diaper-surface sensing reports a rise of about 0.5 to 2 C at the brief surface on voiding, and wet material later reads cooler than dry material as it evaporates. No public labelled thermal-incontinence dataset was found, so real data has to come from a bench.

Bench protocol. Mount the MLX90640 over a bed with a person or a warm mannequin (a heating pad set to body temperature works) under a pad and blanket. Run `tools/record_mlx.py`, and pour 150 to 300 ml of 37 C saline onto the pad, pressing `v` as you pour. Repeat across blanket thicknesses and pour volumes, and add some dry runs with turns (`t`) and hands (`h`/`j`). Ten wet and ten dry runs are enough to tune the thresholds honestly. It is not clinical data, but it is real sensor data from the hardware.

Position data. PMD can be downloaded with no approval: 13 subjects, 17 posture files each, 32x64 pressure frames at 1 Hz. It is a pressure mat, not a camera, but the feature code is sensor-agnostic so the same classifier and turn logic get exercised on real human data. SLP (109 people, thermal plus RGB, three cover conditions) is the closer match to overhead thermal. Plug it in when access lands. Do not invent SLP numbers.

Skin check.

- PIID is 1,091 physician-labelled images across four stages, and it is described as the only public set covering all four stages with expert labels. It has no healthy skin and no patient IDs, which is why negatives come from PI-Net's masked images and near-duplicate photos are grouped before splitting.
- Independent results on PIID sit around 77 to 81% for four-class staging, while hospital-internal papers report 92% and up. Expect the lower range.
- A 2025 study found a model trained on one dataset dropped to 75% on fresh images from a new hospital and rose to 89% after training with realistic noise like healing tissue. That is why colour constancy, abstention, and a nurse-only result are required.

## Sources

- PhysioNet PMD: https://physionet.org/content/pmd/1.0.0 (Pouyan et al., IEEE BHI 2017)
- SLP: arXiv 2008.08735 and 1907.02161; https://github.com/ostadabbas/SLP-Dataset-and-Code
- PIID: https://github.com/FU-MedicalAI/PIID (Ay et al., Neural Computing and Applications 2022)
- PI-Net masks and MIPI: https://github.com/clare304/PI-Net
- FT-ARM PIID benchmark: arXiv 2510.24980 (not used; it is a generative model)
- Saliency-guided PU staging generalisation: Diagnostics 2025, doi 10.3390/diagnostics15232951
- Diaper surface temperature on voiding: US patent 9545342; related thermal voiding detection US11504280B2
- Grid-EYE in-bed monitoring: arXiv 2107.07986
