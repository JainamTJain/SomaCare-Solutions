"""SLP (Northeastern ACLab, access by request: github.com/ostadabbas/SLP-Dataset-and-Code).
LWIR frames are 160x120. We downsample to 24x32 to imitate an MLX90640 so the model is
trained at the resolution we will actually deploy, and we keep all three cover conditions
(uncover / cover1 thin sheet / cover2 blanket) and report accuracy per cover.
SLP collects 15 poses per category; confirm the index->category order in the dataset readme
(expected: 1-15 supine, 16-30 left, 31-45 right) before training."""
import numpy as np
from .features import to_grid

POSE_BLOCKS_VERIFIED = False
def pose_idx_to_class(i):            # 1-based index -> 0 supine, 1 left, 2 right
    return (i - 1) // 15

def to_mlx_like(ir_frame, noise_sd_c=0.1, rng=None):
    rng = rng or np.random.default_rng()
    g = to_grid(ir_frame.astype(np.float32), (24, 32))
    return g + rng.normal(0, noise_sd_c, g.shape).astype(np.float32)
