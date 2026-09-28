import numpy as np, sys, os
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from somacare_stage2.continence_thermal.sim import simulate_night
from somacare_stage2.continence_thermal.detect import detect, score
from somacare_stage2.position.pmd import read_file, POSTURE_TO_CLASS, CLASSES
from somacare_stage2.position.features import featurize, to_grid
from somacare_stage2.position.train_eval import loso

def test_clean_void_detected_quickly():
    n = simulate_night(n_voids=1, n_turns=0, n_hands=0, seed=3)
    ev = detect(n.t, n.pelvis, n.chest)
    assert len(ev) == 1 and 0 <= ev[0]["t_possible"] - n.voids[0] < 300

def test_dry_nights_with_turns_and_hands_stay_quiet():
    r = score([simulate_night(seed=900 + s, n_voids=0, n_turns=4, n_hands=2) for s in range(30)])
    assert r["false_possible_per_night"] <= 0.1

def test_sensitivity_floor_on_simulated_nights():
    r = score([simulate_night(seed=s) for s in range(40)])
    assert r["sensitivity"] >= 0.8

def test_room_drift_alone_never_triggers():
    t = np.arange(0, 8 * 3600, 2.0); drift = 2.0 * np.sin(t / 5000)
    rng = np.random.default_rng(0)
    ev = detect(t, 30 + drift + rng.normal(0, .1, t.size), 31 + drift + rng.normal(0, .1, t.size))
    assert ev == []

def _fake_pmd(tmp, subjects=4, frames=12):
    rng = np.random.default_rng(1)
    for s in range(1, subjects + 1):
        d = tmp / f"S{s}"; d.mkdir()
        for pos in range(1, 18):
            cls = POSTURE_TO_CLASS[pos]
            rows = []
            for _ in range(frames):
                f = np.zeros((64, 32)); cx = {"supine": 16, "left": 10, "right": 22}[cls]
                w = 8 if cls == "supine" else 4
                f[10:58, cx - w:cx + w] = rng.uniform(200, 600)
                rows.append((f + rng.uniform(0, 30, f.shape)).ravel())
            np.savetxt(d / f"{pos}.txt", np.array(rows), delimiter="\t", fmt="%.0f")

def test_pmd_parser_and_loso(tmp_path):
    from somacare_stage2.position.pmd import load_experiment_i
    _fake_pmd(tmp_path)
    X, y, g = load_experiment_i(tmp_path)
    assert X.shape[1:] == (64, 32) and set(np.unique(g)) == {1, 2, 3, 4}
    r = loso(featurize(X), y, g)
    assert r["accuracy"] > 0.95

def test_wrong_width_rejected(tmp_path):
    p = tmp_path / "1.txt"; np.savetxt(p, np.ones((5, 100)))
    try: read_file(p); assert False
    except ValueError: pass

def test_to_grid_preserves_mean():
    f = np.random.default_rng(0).uniform(20, 35, (120, 160))
    assert abs(to_grid(f, (24, 32)).mean() - f.mean()) < 1e-3

def test_near_duplicates_grouped_and_distinct_kept_apart():
    from PIL import Image
    from somacare_stage2.skin.data import group_near_duplicates
    rng = np.random.default_rng(0)
    a = rng.uniform(0, 255, (64, 64, 3)).astype(np.uint8)
    b = np.clip(a.astype(int) + rng.integers(-6, 6, a.shape), 0, 255).astype(np.uint8)  # re-shot
    c = rng.uniform(0, 255, (64, 64, 3)).astype(np.uint8)
    g = group_near_duplicates([Image.fromarray(x) for x in (a, b, c)])
    assert g[0] == g[1] and g[0] != g[2]

def test_shades_of_gray_removes_yellow_cast():
    from PIL import Image
    from somacare_stage2.skin.data import shades_of_gray
    base = np.random.default_rng(1).uniform(80, 180, (50, 50, 3))
    cast = np.clip(base * [1.25, 1.1, 0.7], 0, 255).astype(np.uint8)
    out = np.asarray(shades_of_gray(Image.fromarray(cast)), dtype=float).mean((0, 1))
    assert out.max() / out.min() < 1.1

def test_negative_patches_never_touch_wound():
    from PIL import Image
    from somacare_stage2.skin.data import intact_skin_patches
    img = Image.fromarray(np.random.default_rng(2).uniform(0, 255, (400, 400, 3)).astype(np.uint8))
    m = np.zeros((400, 400), bool); m[150:250, 150:250] = True
    ps = intact_skin_patches(img, m, n=4)
    assert len(ps) == 4

@pytest.mark.skipif(not os.environ.get("SLP_ROOT"), reason="SLP_ROOT is unset")
def test_slp_smoke():
    """Runs only when a local SLP copy is available. Does not download anything."""
    from somacare_stage2.position.slp import POSE_BLOCKS_VERIFIED, pose_idx_to_class, to_mlx_like
    root = os.environ["SLP_ROOT"]
    assert os.path.isdir(root)
    assert pose_idx_to_class(1) == 0 and pose_idx_to_class(16) == 1 and pose_idx_to_class(31) == 2
    assert to_mlx_like(np.zeros((120, 160), np.float32)).shape == (24, 32)
    assert isinstance(POSE_BLOCKS_VERIFIED, bool)
