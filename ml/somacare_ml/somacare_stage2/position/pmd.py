"""PhysioNet PMD (open access, ODC-By 1.0). Experiment I: 13 subjects, 17 posture files each,
~120 frames at 1 Hz, each row = 2048 values = one 64x32 pressure frame (values 0-1000).
Download:  wget -r -N -c -np https://physionet.org/files/pmd/1.0.0/

LABEL MAP: verify against experiment-info.docx before trusting results. The map below is the
one commonly used in papers on this dataset (1 supine, 2 right, 3 left, 4-5 right 30/60 deg,
6-7 left 30/60 deg, 8-17 supine variants). Set LABELS_VERIFIED = True only after a human
has opened the docx and confirmed it."""
from pathlib import Path
import numpy as np

LABELS_VERIFIED = False
POSTURE_TO_CLASS = {1: "supine", 2: "right", 3: "left", 4: "right", 5: "right",
                    6: "left", 7: "left", **{k: "supine" for k in range(8, 18)}}
CLASSES = ["supine", "left", "right"]

def read_file(path, drop_first=3):
    """Returns (n_frames, 64, 32) float32. First frames are often the subject settling."""
    a = np.loadtxt(path, dtype=np.float32, ndmin=2)
    if a.shape[1] != 2048:
        raise ValueError(f"{path}: expected 2048 columns, got {a.shape[1]}")
    a = a[drop_first:] if a.shape[0] > drop_first + 5 else a
    return a.reshape(-1, 64, 32)

def load_experiment_i(root):
    """root = .../pmd/1.0.0/experiment-i ; returns X (N,64,32), y (N,), subj (N,)"""
    X, y, g = [], [], []
    for sdir in sorted(Path(root).glob("S*")):
        sid = int(sdir.name[1:])
        for f in sorted(sdir.glob("*.txt"), key=lambda p: int(p.stem)):
            pos = int(f.stem)
            if pos not in POSTURE_TO_CLASS: continue
            fr = read_file(f)
            X.append(fr); y += [CLASSES.index(POSTURE_TO_CLASS[pos])] * len(fr); g += [sid] * len(fr)
    return np.concatenate(X), np.array(y), np.array(g)
