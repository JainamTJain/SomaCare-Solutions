"""Filesystem roots that stay inside backend/ so a Render root directory works."""

from __future__ import annotations

from pathlib import Path

from turnwise.settings import setting

# backend/turnwise/paths.py -> backend/
BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent


def data_dir() -> Path:
    override = setting("DATA_DIR")
    path = Path(override) if override else BACKEND_ROOT / "var"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_config_path() -> Path:
    override = setting("CONFIG")
    if override:
        return Path(override)
    bundled = BACKEND_ROOT / "config" / "turnwise.yaml"
    if bundled.is_file():
        return bundled
    return REPO_ROOT / "config" / "turnwise.yaml"
