"""Two small models, no generative AI anywhere:
  A. wound_present: intact-skin patches (from PI-Net MIPI, outside masks) vs any PI image
  B. stage: Stage 1-4, only consulted when A says 'wound'
Output is never a diagnosis. It is 'nurse review suggested: looks like Stage N at <site>'
or 'unsure' (abstain) -- see ABSTAIN_BELOW.
Honesty bar: independent benchmarks on PIID land around 77-81% for 4-class staging. If a
fold here reports >90%, assume leakage (near-duplicates across folds) and investigate."""
import json, sys
import numpy as np, torch, torch.nn as nn
from PIL import Image
from sklearn.model_selection import StratifiedGroupKFold
from torchvision import models, transforms as T
from .data import load_piid, group_near_duplicates, shades_of_gray

ABSTAIN_BELOW = 0.6          # calibrated max-prob; below -> 'unsure, nurse look'
DEV = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
NORM = T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
TRAIN_TF = T.Compose([T.RandomResizedCrop(224, scale=(0.6, 1.0)), T.RandomHorizontalFlip(),
    T.RandomVerticalFlip(), T.RandomRotation(20),
    T.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.1),   # NO hue jitter: redness is the signal
    T.ToTensor(), NORM])
EVAL_TF = T.Compose([T.Resize(256), T.CenterCrop(224), T.ToTensor(), NORM])

class DS(torch.utils.data.Dataset):
    def __init__(s, paths, y, tf): s.p, s.y, s.tf = paths, y, tf
    def __len__(s): return len(s.p)
    def __getitem__(s, i): return s.tf(shades_of_gray(Image.open(s.p[i]).convert("RGB"))), int(s.y[i])

def net(n):
    m = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.IMAGENET1K_V1)
    m.classifier[1] = nn.Linear(m.classifier[1].in_features, n); return m.to(DEV)

def fit(m, dl, y, epochs=25):
    w = torch.tensor(len(y) / (len(np.unique(y)) * np.bincount(y)), dtype=torch.float32, device=DEV)
    opt = torch.optim.AdamW(m.parameters(), 3e-4, weight_decay=1e-4)
    sch = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epochs)
    lossf = nn.CrossEntropyLoss(weight=w, label_smoothing=0.05)
    for _ in range(epochs):
        m.train()
        for x, t in dl:
            opt.zero_grad(); lossf(m(x.to(DEV)), t.to(DEV)).backward(); opt.step()
        sch.step()

@torch.no_grad()
def logits(m, dl):
    m.eval(); L, Y = [], []
    for x, t in dl:
        L.append((m(x.to(DEV)) + m(torch.flip(x, [3]).to(DEV))) / 2); Y.append(t)   # flip TTA
    return torch.cat(L).cpu(), torch.cat(Y).numpy()

def temperature(L, y):
    T_ = torch.ones(1, requires_grad=True); opt = torch.optim.LBFGS([T_], lr=0.1, max_iter=100)
    yt = torch.tensor(y)
    def c(): opt.zero_grad(); l = nn.functional.cross_entropy(L / T_, yt); l.backward(); return l
    opt.step(c); return float(T_.detach())

def main(piid_root, out="skin_report.json", folds=5):
    paths, y = load_piid(piid_root)
    groups = group_near_duplicates([Image.open(p).convert("RGB") for p in paths])
    print(f"{len(paths)} images, {groups.max()+1} near-duplicate groups")
    cms, rep = np.zeros((4, 4), int), {}
    for k, (tr, te) in enumerate(StratifiedGroupKFold(folds, shuffle=True, random_state=0).split(paths, y, groups)):
        # carve a calibration split out of train, also grouped
        trr, cal = next(StratifiedGroupKFold(5, shuffle=True, random_state=k).split(tr, y[tr], groups[tr]))
        trr, cal = tr[trr], tr[cal]
        mk = lambda idx, tf, sh: torch.utils.data.DataLoader(DS([paths[i] for i in idx], y[idx], tf), 32, shuffle=sh, num_workers=2)
        m = net(4); fit(m, mk(trr, TRAIN_TF, True), y[trr])
        Tc = temperature(*logits(m, mk(cal, EVAL_TF, False)))
        L, yt = logits(m, mk(te, EVAL_TF, False)); P = torch.softmax(L / Tc, 1).numpy()
        pred, conf = P.argmax(1), P.max(1); keep = conf >= ABSTAIN_BELOW
        for a, b in zip(yt[keep], pred[keep]): cms[a, b] += 1
        rep[f"fold{k}"] = dict(acc_all=float((pred == yt).mean()), acc_answered=float((pred[keep] == yt[keep]).mean()),
                               abstain_rate=float(1 - keep.mean()), T=Tc)
        torch.save(m.state_dict(), f"stage_fold{k}.pt"); print(rep[f"fold{k}"])
    rep["confusion_answered"] = cms.tolist()
    rep["recall_per_stage"] = (cms.diagonal() / cms.sum(1).clip(min=1)).round(3).tolist()
    json.dump(rep, open(out, "w"), indent=1); print(json.dumps(rep, indent=1))

if __name__ == "__main__":
    main(sys.argv[1])
