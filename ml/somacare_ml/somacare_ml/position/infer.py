"""Deployable classifier: label, confidence, and an explicit 'unknown' when it is not sure or the person is covered."""
from dataclasses import dataclass
import numpy as np
import joblib
from .features import image_features
from .calibrate import apply_temperature


@dataclass
class Reading:
    label: str            # a position, or 'unknown'
    confidence: float
    reason: str           # 'ok' | 'low_confidence' | 'covered' | 'empty'
    probs: dict


class PositionClassifier:
    def __init__(self, pos_model, classes, background, T=1.0, cover_model=None, cover_classes=None,
                 min_conf=0.70, blanket_block=0.60, bed_box=(30, 6, 100, 108)):
        self.pos_model, self.classes, self.bg, self.T = pos_model, list(classes), background, T
        self.cover_model, self.cover_classes = cover_model, cover_classes
        self.min_conf, self.blanket_block, self.bed_box = min_conf, blanket_block, bed_box

    def predict(self, img) -> Reading:
        f = image_features(img, self.bg, self.bed_box)[None, :]
        P = apply_temperature(self.pos_model.predict_proba(f), self.T)[0]
        probs = {c: float(p) for c, p in zip(self.classes, P)}
        top = int(P.argmax()); label, conf = self.classes[top], float(P[top])
        if label == "out_of_bed":
            return Reading(label, conf, "empty" if conf >= self.min_conf else "low_confidence", probs) \
                if conf >= self.min_conf else Reading("unknown", conf, "low_confidence", probs)
        if self.cover_model is not None:
            pc = self.cover_model.predict_proba(f)[0]
            pb = float(pc[self.cover_classes.index("blanket")])
            if pb >= self.blanket_block:
                return Reading("unknown", conf, "covered", probs)
        if conf < self.min_conf:
            return Reading("unknown", conf, "low_confidence", probs)
        return Reading(label, conf, "ok", probs)

    def save(self, path):
        joblib.dump(self, path)

    @staticmethod
    def load(path):
        return joblib.load(path)
