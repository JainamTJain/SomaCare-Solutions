"""Train and evaluate the position classifier, holding out whole people.

Usage from code:
    ds = [(image, label, person, cover), ...]          # from synth.make_dataset(...) or dataset.load_dataset(...)
    report, clf = train_and_evaluate(ds, background)   # leave-one-person-out report, then a final fit on everyone
"""
import numpy as np
from collections import defaultdict
from sklearn.ensemble import HistGradientBoostingClassifier
from .features import image_features, flip_image, swap_lr
from .calibrate import fit_temperature, apply_temperature, ece_top_label
from .infer import PositionClassifier


def _model():
    return HistGradientBoostingClassifier(max_iter=180, learning_rate=0.08, max_leaf_nodes=15,
                                          l2_regularization=1.0, class_weight="balanced", random_state=0)


def featurize(ds, background, flip_augment=True, bed_box=(30, 6, 100, 108)):
    X, y, person, cover = [], [], [], []
    for img, label, p, c in ds:
        X.append(image_features(img, background, bed_box)); y.append(label); person.append(p); cover.append(c)
        if flip_augment:      # mirror the frame and swap the side label. Never skip the swap.
            X.append(image_features(flip_image(img), background, bed_box)); y.append(swap_lr(label))
            person.append(p); cover.append(c)
    return np.array(X), np.array(y), np.array(person), np.array(cover)


def train_and_evaluate(ds, background, min_conf=0.70, flip_augment=True, bed_box=(30, 6, 100, 108)):
    X, y, person, cover = featurize(ds, background, flip_augment, bed_box)
    classes = sorted(set(y))
    yi = np.array([classes.index(v) for v in y])
    people = sorted(set(person.tolist()))
    oof = np.zeros((len(y), len(classes)))
    oof_cover = np.zeros((len(y), 3))
    cover_classes = ["blanket", "none", "sheet"]
    ci = np.array([cover_classes.index(c) for c in cover])
    for p in people:
        tr, te = person != p, person == p
        m = _model().fit(X[tr], yi[tr])
        oof[te] = m.predict_proba(X[te])
        cm = _model().fit(X[tr], ci[tr])
        oof_cover[te] = cm.predict_proba(X[te])
    T = fit_temperature(oof, yi)
    P = apply_temperature(oof, T)
    pred = P.argmax(axis=1); conf = P.max(axis=1)
    blanket_p = oof_cover[:, cover_classes.index("blanket")]

    def summarize(mask):
        if mask.sum() == 0:
            return None
        ok = pred[mask] == yi[mask]
        sure = (conf[mask] >= min_conf) & (blanket_p[mask] < 0.6)
        # accuracy counted over ALL frames, treating 'unknown' as not a correct claim, and over claimed frames only
        acc_all = float(np.mean(ok & sure))
        acc_claimed = float(np.mean(ok[sure])) if sure.any() else float("nan")
        return dict(n=int(mask.sum()), accuracy_all=acc_all, accuracy_when_claimed=acc_claimed,
                    unknown_rate=float(1 - sure.mean()))

    by_cover = {c: summarize(cover == c) for c in ["none", "sheet", "blanket"]}
    overall = summarize(np.ones(len(y), bool))
    lr_pairs = [(classes.index("left"), classes.index("right")), (classes.index("right"), classes.index("left"))]
    sided = np.isin(yi, [classes.index("left"), classes.index("right")])
    lr_conf = float(np.mean([(pred[i] == swap_i) for i, swap_i in
                             [(k, classes.index(swap_lr(classes[yi[k]]))) for k in np.nonzero(sided)[0]]])) if sided.any() else float("nan")
    cm_full = np.zeros((len(classes), len(classes)), int)
    for a, b in zip(yi, pred):
        cm_full[a, b] += 1
    report = dict(classes=classes, people_held_out=len(people), temperature=T,
                  ece=ece_top_label(P, yi), overall=overall, by_cover=by_cover,
                  left_right_confusion=lr_conf, confusion_matrix=cm_full.tolist(), min_conf=min_conf)

    pos_model = _model().fit(X, yi)
    cover_model = _model().fit(X, ci)
    clf = PositionClassifier(pos_model, classes, background, T=T, cover_model=cover_model,
                             cover_classes=cover_classes, min_conf=min_conf, bed_box=bed_box)
    return report, clf


def confusion_from_report(report):
    """Row-normalized confusion, ready to feed the safety simulation."""
    cm = np.array(report["confusion_matrix"], float)
    return cm / np.clip(cm.sum(axis=1, keepdims=True), 1, None)
