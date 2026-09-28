"""Bath-photo scanner using a published, pretrained model. We do not train anything.
Model: Joy-Diganta/pressure-ulcer-classifier (MIT licence), ConvNeXt-V2 Base at 384x384,
7 classes including 'Invalid' (not a pressure injury / not a usable photo). The author reports
84.39% validation accuracy. Preprocessing matches the author's app.py exactly.
Get the weights with tools/get_skin_model.sh. Output is a suggestion; a nurse confirms."""
import io, os
from pathlib import Path

CKPT = os.environ.get("SKIN_CKPT", "models/pu_convnextv2_fold0.pth")
ABSTAIN_BELOW = float(os.environ.get("SKIN_ABSTAIN", "0.5"))
ARCH = "convnextv2_base.fcmae_ft_in22k_in1k_384"
CLASS_NAMES = ["Invalid", "SDTI", "Stage_I", "Stage_II", "Stage_III", "Stage_IV", "Unstageable"]
SOURCE = "ConvNeXt-V2 pressure-ulcer classifier (Joy-Diganta, MIT)"
# model class -> engine finding (engine: intact < blanch < stage1 < stage2-or-deeper)
TO_FINDING = {"Invalid": "intact", "Stage_I": "stage1", "Stage_II": "stage2", "Stage_III": "stage2",
              "Stage_IV": "stage2", "SDTI": "stage2", "Unstageable": "stage2"}
SAYS = {"Invalid": "no pressure injury seen (or not a usable skin photo)",
        "SDTI": "possible deep tissue injury", "Stage_I": "looks like Stage 1",
        "Stage_II": "looks like Stage 2", "Stage_III": "looks like Stage 3",
        "Stage_IV": "looks like Stage 4", "Unstageable": "looks unstageable (wound base hidden)"}
_model = None

def _load():
    global _model
    if _model is not None or not Path(CKPT).exists(): return _model
    import torch, timm
    ck = torch.load(CKPT, map_location="cpu", weights_only=False)
    m = timm.create_model(ARCH, pretrained=False, num_classes=len(CLASS_NAMES))
    m.load_state_dict(ck["model_state_dict"] if isinstance(ck, dict) and "model_state_dict" in ck else ck, strict=True)
    m.eval(); _model = m; return m

def interpret(probs):
    """probs: 7 floats in CLASS_NAMES order -> suggestion dict. Pure Python, unit-tested."""
    k = max(range(len(probs)), key=lambda i: probs[i]); name, conf = CLASS_NAMES[k], probs[k]
    out = dict(label=name, confidence=round(conf, 3), model=SOURCE,
               probs={n: round(p, 3) for n, p in zip(CLASS_NAMES, probs)})
    if conf < ABSTAIN_BELOW:
        return dict(out, status="unsure", finding=None, message=f"unsure ({conf:.0%}); nurse look needed")
    if name == "Invalid":
        return dict(out, status="no_injury", finding="intact", message=f"{SAYS[name]} ({conf:.0%})")
    return dict(out, status="ok", finding=TO_FINDING[name], message=f"{SAYS[name]} ({conf:.0%}); nurse review suggested")

def suggest(image_bytes):
    m = _load()
    if m is None:
        return dict(status="model_not_loaded", finding=None,
                    message=f"no skin model found at {CKPT}; run tools/get_skin_model.sh")
    import torch
    from PIL import Image
    from torchvision import transforms as T
    tf = T.Compose([T.Resize((384, 384)), T.ToTensor(),
                    T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])
    x = tf(Image.open(io.BytesIO(image_bytes)).convert("RGB")).unsqueeze(0)
    with torch.no_grad():
        p = torch.softmax(m(x), dim=1)[0].tolist()
    return interpret(p)
