"""Train Model A on SLP. Refuses to claim a clinical model without the dataset.

The recipe matches the engineering spec. Run only on a machine where SLP has
been requested from the ACLab and the license has been recorded in
docs/data_licenses.md. This environment does not download SLP.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))

from datasets.slp import training_recipe  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slp-root", type=Path, default=None)
    args = parser.parse_args()
    recipe = training_recipe()
    if args.slp_root is None or not args.slp_root.exists():
        raise SystemExit(
            "SLP is not on this machine. Request it from the Northeastern ACLab, "
            "record the license in docs/data_licenses.md, and pass --slp-root. "
            f"The training recipe is ready: {recipe['optimizer']} lr={recipe['learning_rate']}."
        )
    try:
        import torch  # noqa: F401
    except ImportError as exc:
        raise SystemExit("PyTorch is required to train Model A. See requirements-ml.txt.") from exc
    raise SystemExit(
        "Loader is wired. Training starts once subject-wise SLP splits are pointed at real files."
    )


if __name__ == "__main__":
    main()
