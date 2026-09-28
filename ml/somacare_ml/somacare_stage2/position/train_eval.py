"""Leave-one-subject-out evaluation (never random frame splits: adjacent frames of one person
are near-duplicates and inflate accuracy). Reports per-class recall and the worst subject."""
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import confusion_matrix

def make_model():
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=0.5))

def loso(F, y, groups, n_classes=3):
    cm = np.zeros((n_classes, n_classes), int); per_subject = {}
    for s in np.unique(groups):
        tr, te = groups != s, groups == s
        m = make_model().fit(F[tr], y[tr]); pr = m.predict(F[te])
        cm += confusion_matrix(y[te], pr, labels=range(n_classes))
        per_subject[int(s)] = float((pr == y[te]).mean())
    recall = cm.diagonal() / cm.sum(1).clip(min=1)
    return dict(confusion=cm.tolist(), recall=recall.round(3).tolist(),
                accuracy=round(float(cm.diagonal().sum() / cm.sum()), 3),
                worst_subject=min(per_subject.items(), key=lambda kv: kv[1]))

if __name__ == "__main__":
    import sys, json
    from .pmd import load_experiment_i, LABELS_VERIFIED
    from .features import featurize
    X, y, g = load_experiment_i(sys.argv[1])
    print("labels verified:", LABELS_VERIFIED, "frames:", len(X))
    print(json.dumps(loso(featurize(X), y, g), indent=1))
