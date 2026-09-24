"""Persistent user settings stored as JSON in %APPDATA%\\Umbra."""

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

from . import paths

log = logging.getLogger(__name__)

MODES = ("blur", "image", "media", "color")
MODE_LABELS = {
    "blur": "Blur",
    "image": "Custom image",
    "media": "Animated GIF / video",
    "color": "Solid color",
}
FIT_MODES = ("cover", "contain", "stretch")


@dataclass
class Settings:
    # General
    enabled: bool = True
    hotkey: str = "F8"
    autostart: bool = False
    notifications: bool = True
    camera_index: int = 0
    first_run: bool = True

    # Detection
    yaw_threshold: float = 28.0          # degrees left/right
    pitch_up_threshold: float = 22.0     # degrees looking up
    pitch_down_threshold: float = 32.0   # degrees looking down (lenient: keyboard glances)
    use_eye_gaze: bool = True
    eye_gaze_threshold: float = 0.60     # 0..1 sideways eye-look score
    away_delay_ms: int = 700
    return_delay_ms: int = 150
    blur_when_no_face: bool = True
    blur_on_extra_face: bool = False
    process_fps: int = 15
    yaw_offset: float = 0.0              # calibration: neutral pose
    pitch_offset: float = 0.0
    calibrated: bool = False             # guided calibration completed at least once

    # Appearance
    mode: str = "blur"
    blur_strength: int = 45              # 1..100
    live_blur: bool = True
    dim: int = 15                        # 0..90 % darkening
    image_path: str = ""
    media_path: str = ""
    media_fit: str = "cover"
    color: str = "#0f0f13"             # Umbra ink
    show_message: bool = True
    message: str = "Look at your screen to continue"
    fade_ms: int = 160

    def copy(self) -> "Settings":
        return replace(self)

    def validated(self) -> "Settings":
        """Return a copy with every value coerced into its valid range."""
        s = self.copy()

        def clamp(v, lo, hi):
            return max(lo, min(hi, v))

        s.camera_index = int(clamp(int(s.camera_index), 0, 16))
        s.yaw_threshold = float(clamp(float(s.yaw_threshold), 5.0, 80.0))
        s.pitch_up_threshold = float(clamp(float(s.pitch_up_threshold), 5.0, 80.0))
        s.pitch_down_threshold = float(clamp(float(s.pitch_down_threshold), 5.0, 80.0))
        s.eye_gaze_threshold = float(clamp(float(s.eye_gaze_threshold), 0.1, 1.0))
        s.away_delay_ms = int(clamp(int(s.away_delay_ms), 0, 10000))
        s.return_delay_ms = int(clamp(int(s.return_delay_ms), 0, 5000))
        s.process_fps = int(clamp(int(s.process_fps), 5, 30))
        s.yaw_offset = float(clamp(float(s.yaw_offset), -60.0, 60.0))
        s.pitch_offset = float(clamp(float(s.pitch_offset), -60.0, 60.0))
        s.blur_strength = int(clamp(int(s.blur_strength), 1, 100))
        s.dim = int(clamp(int(s.dim), 0, 90))
        s.fade_ms = int(clamp(int(s.fade_ms), 0, 2000))
        if s.mode not in MODES:
            s.mode = "blur"
        if s.media_fit not in FIT_MODES:
            s.media_fit = "cover"
        if not s.hotkey:
            s.hotkey = ""
        return s


def load(path: Path | None = None) -> Settings:
    path = path or paths.settings_file()
    defaults = Settings()
    if not path.is_file():
        return defaults
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("settings root is not an object")
    except Exception:
        log.exception("Could not read settings from %s; using defaults", path)
        return defaults

    values = {}
    for f in fields(Settings):
        if f.name not in raw:
            continue
        default = getattr(defaults, f.name)
        value = raw[f.name]
        try:
            if isinstance(default, bool):
                value = bool(value)
            elif isinstance(default, int):
                value = int(value)
            elif isinstance(default, float):
                value = float(value)
            elif isinstance(default, str):
                value = str(value)
        except (TypeError, ValueError):
            log.warning("Ignoring invalid value for %s: %r", f.name, value)
            continue
        values[f.name] = value
    return replace(defaults, **values).validated()


def save(settings: Settings, path: Path | None = None) -> None:
    """Write settings atomically so a crash never leaves a truncated file."""
    path = path or paths.settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(asdict(settings.validated()), indent=2)
    fd, tmp = tempfile.mkstemp(prefix="settings-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
