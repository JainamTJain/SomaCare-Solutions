"""Bath-photo inference. Loads the Stage 2 checkpoint (EfficientNet-B0, PIID stages 1-4) if
present; otherwise says so honestly and the nurse enters the finding. Output is a suggestion.
A photo cannot show whether redness blanches, so Stage 1 vs blanchable is left to the nurse's
press test; the suggestion maps Stage 1 to 'stage1' only as a provisional, tighten-only value."""
import io, os
from pathlib import Path

CKPT = os.environ.get("SKIN_CKPT", "models/stage_fold0.pt")
ABSTAIN_BELOW = float(os.environ.get("SKIN_ABSTAIN", "0.6"))
MAP = ["stage1", "stage2", "stage2", "stage2"]   # model stages 1..4 -> engine findings
_model = None

def _load():
    global _model
    if _model is not None or not Path(CKPT).exists(): return _model
    import torch, torch.nn as nn
    from torchvision import models
    m = models.efficientnet_b0(weights=None); m.classifier[1] = nn.Linear(m.classifier[1].in_features, 4)
    m.load_state_dict(torch.load(CKPT, map_location="cpu")); m.eval(); _model = m; return m

def suggest(image_bytes):
    m = _load()
    if m is None:
        return dict(status="model_not_loaded", finding=None,
                    message=f"no skin model found at {CKPT}; photo saved for nurse review")
    import numpy as np, torch
    from PIL import Image
    from torchvision import transforms as T
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    a = np.asarray(img, dtype=np.float32) + 1e-6                     # shades-of-gray colour constancy
    illum = np.power(np.mean(np.power(a, 6), axis=(0, 1)), 1 / 6); a = a * (illum.mean() / illum)
    img = Image.fromarray(np.clip(a, 0, 255).astype("uint8"))
    tf = T.Compose([T.Resize(256), T.CenterCrop(224), T.ToTensor(),
                    T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])
    with torch.no_grad():
        x = tf(img).unsqueeze(0); p = torch.softmax((m(x) + m(torch.flip(x, [3]))) / 2, 1)[0].tolist()
    k = max(range(4), key=lambda i: p[i]); conf = p[k]
    if conf < ABSTAIN_BELOW:
        return dict(status="unsure", finding=None, probs=p, message=f"unsure ({conf:.0%}); nurse look needed")
    return dict(status="ok", finding=MAP[k], probs=p, stage=k + 1,
                message=f"looks like Stage {k + 1} ({conf:.0%}); nurse review suggested")
