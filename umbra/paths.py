"""Filesystem locations used by the application."""

import os
import shutil
import sys
from pathlib import Path

from . import APP_NAME

MODEL_FILENAME = "face_landmarker.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)


def resource_root() -> Path:
    """Directory holding bundled read-only resources (works under PyInstaller)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


LEGACY_NAMES = ("FocusBlur",)  # earlier product names whose settings we carry over


def data_dir() -> Path:
    """Per-user writable directory for settings, logs and downloaded models."""
    base = Path(os.environ.get("APPDATA") or str(Path.home() / ".config"))
    path = base / APP_NAME
    if not path.exists():
        _migrate_legacy(base, path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _migrate_legacy(base: Path, target: Path) -> None:
    for name in LEGACY_NAMES:
        old = base / name / "settings.json"
        if old.is_file():
            try:
                target.mkdir(parents=True, exist_ok=True)
                shutil.copy2(old, target / "settings.json")
            except OSError:
                pass
            return


def settings_file() -> Path:
    return data_dir() / "settings.json"


def log_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def bundled_model() -> Path:
    return resource_root() / "assets" / "models" / MODEL_FILENAME


def downloaded_model() -> Path:
    return data_dir() / "models" / MODEL_FILENAME


def find_model() -> Path | None:
    for candidate in (bundled_model(), downloaded_model()):
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    return None
