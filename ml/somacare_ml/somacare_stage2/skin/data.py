"""Data prep for the bath-time skin check.

Sources (download manually, licences differ; record them in DATA_SOURCES.md):
  PIID   github.com/FU-MedicalAI/PIID -> Google Drive link in README. 1,091 RGB, 299x299,
         Stage-1..4 folders, labelled by physicians (EPUAP). Injuries only: NO healthy skin,
         NO patient IDs.
  PI-Net github.com/clare304/PI-Net -> Zenodo: 406 high-res 'MIPI' images + masks, plus
         wound masks and NPIAP stage labels re-done by wound specialists for 980 PIID images.
Two traps this file exists to defuse:
  1. Leakage: PIID has several photos of the same wound. Random splits put near-twins in
     train and test and inflate accuracy. We group near-duplicates by perceptual hash and
     split by group.
  2. No negatives: a 'which stage' model cannot say 'no wound'. We cut intact-skin patches
     from MIPI images OUTSIDE the dilated wound mask -> same cameras/lighting, honest negatives."""
from pathlib import Path
import numpy as np
from PIL import Image

STAGES = ["Stage-1", "Stage-2", "Stage-3", "Stage-4"]

def ahash(img, size=16):
    g = np.asarray(img.convert("L").resize((size, size), Image.BILINEAR), dtype=np.float32)
    return (g > g.mean()).ravel()

def group_near_duplicates(images, max_hamming=20):
    """Union-find over average-hash distance. Returns group id per image."""
    hs = [ahash(im) for im in images]; n = len(hs); parent = list(range(n))
    def find(a):
        while parent[a] != a: parent[a] = parent[parent[a]]; a = parent[a]
        return a
    for i in range(n):
        for j in range(i + 1, n):
            if np.count_nonzero(hs[i] != hs[j]) <= max_hamming:
                parent[find(i)] = find(j)
    roots = {r: k for k, r in enumerate(sorted({find(i) for i in range(n)}))}
    return np.array([roots[find(i)] for i in range(n)])

def shades_of_gray(img, p=6):
    """Colour constancy (standard in dermoscopy). Phone photos under yellow bathroom light
    otherwise shift the red channel, which is exactly the Stage 1 signal."""
    a = np.asarray(img, dtype=np.float32) + 1e-6
    illum = np.power(np.mean(np.power(a, p), axis=(0, 1)), 1 / p)
    a = a * (illum.mean() / illum)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))

def load_piid(root):
    paths, labels = [], []
    for k, s in enumerate(STAGES):
        for p in sorted((Path(root) / s).glob("*")):
            if p.suffix.lower() in {".jpg", ".jpeg", ".png"}: paths.append(p); labels.append(k)
    return paths, np.array(labels)

def intact_skin_patches(img, mask, n=4, size=112, dilate_px=40, rng=None):
    """Patches whose dilated-mask overlap is zero. mask: HxW bool (wound=True)."""
    from scipy.ndimage import binary_dilation
    rng = rng or np.random.default_rng(0)
    m = binary_dilation(mask, iterations=dilate_px)
    a = np.asarray(img); H, W = m.shape; out = []
    for _ in range(n * 30):
        if len(out) == n or H <= size or W <= size: break
        y, x = rng.integers(0, H - size), rng.integers(0, W - size)
        crop = a[y:y + size, x:x + size]
        if not m[y:y + size, x:x + size].any() and crop.std() > 8:   # skip flat background
            out.append(Image.fromarray(crop))
    return out
