"""Write docs/openapi.json from the FastAPI app.

    python scripts/export_openapi.py
    python scripts/export_openapi.py --check
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for entry in (ROOT / "backend", ROOT / "ml", ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

os.environ.setdefault("SOMACARE_DATABASE_URL", f"sqlite:///{ROOT / 'backend' / 'var' / 'openapi.db'}")
os.environ.setdefault("SOMACARE_CARE_CLOCK", "0")
os.environ.setdefault("SOMACARE_SECRET", "openapi-export")


def spec_text() -> str:
    from turnwise.main import app

    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    target = ROOT / "docs" / "openapi.json"
    text = spec_text()
    if "--check" in sys.argv:
        current = target.read_text() if target.is_file() else ""
        if current != text:
            print("docs/openapi.json is out of date. Run: python scripts/export_openapi.py", file=sys.stderr)
            return 1
        print("docs/openapi.json matches the app")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
