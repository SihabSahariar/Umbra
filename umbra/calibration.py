"""Guided calibration: which poses to record and how to turn them into thresholds.

The user looks at the screen centre, at each screen edge (poses that must stay
*unblurred*) and then away from the screen in every direction (poses that must
*blur*). Each threshold is placed between the furthest on-screen pose and the
nearest away pose, so the limits fit this user, camera and monitor.
"""

from dataclasses import dataclass, field

import numpy as np

MIN_SAMPLES = 5


@dataclass(frozen=True)
class Step:
    key: str
    title: str
    instruction: str
    on_screen: bool


STEPS: tuple[Step, ...] = (
    Step("center", "Centre of the screen",
         "Sit as you normally do and look at the dot in the centre of your screen.", True),
    Step("screen_left", "Left edge of the screen",
         "Look at the arrow on the LEFT edge of your screen, as you would when reading there.", True),
    Step("screen_right", "Right edge of the screen",
         "Look at the arrow on the RIGHT edge of your screen.", True),
    Step("screen_top", "Top of the screen",
         "Look at the arrow at the TOP of your screen.", True),
    Step("screen_bottom", "Bottom of the screen",
         "Look at the arrow at the BOTTOM of your screen (e.g. the taskbar).", True),
    Step("away_left", "Look away to the left",
         "Turn your head to the LEFT, away from the screen, like talking to someone beside you.", False),
    Step("away_right", "Look away to the right",
         "Turn your head to the RIGHT, away from the screen.", False),
    Step("away_up", "Look up, away from the screen",
         "Look UP above your monitor, toward the wall or ceiling.", False),
    Step("away_down", "Look down, away from the screen",
         "Look DOWN at your lap or your phone, below the desk.", False),
    Step("eyes_away", "Glance away with your eyes only",
         "Keep your head still and move only your EYES to the side, past the edge of the screen.", False),
)


@dataclass
class Pose:
    yaw: float
    pitch: float
    eye: float  # absolute sideways eye-look score


def summarize(samples) -> Pose | None:
    """Robust (median) pose from raw (yaw, pitch, eye_h) samples."""
    if len(samples) < MIN_SAMPLES:
        return None
    arr = np.asarray(samples, dtype=float)
    return Pose(float(np.median(arr[:, 0])), float(np.median(arr[:, 1])), float(np.median(np.abs(arr[:, 2]))))


@dataclass
class CalibrationResult:
    yaw_offset: float
    pitch_offset: float
    yaw_threshold: float
    pitch_up_threshold: float
    pitch_down_threshold: float
    eye_gaze_threshold: float
    warnings: list[str] = field(default_factory=list)

    def apply_to(self, settings) -> None:
        settings.yaw_offset = self.yaw_offset
        settings.pitch_offset = self.pitch_offset
        settings.yaw_threshold = self.yaw_threshold
        settings.pitch_up_threshold = self.pitch_up_threshold
        settings.pitch_down_threshold = self.pitch_down_threshold
        settings.eye_gaze_threshold = self.eye_gaze_threshold


def _boundary(edge: float, away: float, label: str, warnings: list[str],
              min_gap: float = 6.0, fallback_margin: float = 10.0) -> float:
    """Pick a limit beyond `edge` (must not blur) but before `away` (must blur)."""
    if away < edge + min_gap:
        warnings.append(
            f"{label}: looking away ({away:.0f}°) was too close to looking at the screen edge "
            f"({edge:.0f}°). A default margin was used - you can redo this step."
        )
        return edge + fallback_margin
    # Lean slightly toward the screen edge: privacy matters more than a few extra degrees.
    return max(edge + 4.0, edge + 0.45 * (away - edge))


def _clamp(v: float, lo: float, hi: float) -> float:
    return round(max(lo, min(hi, v)), 1)


def compute(poses: dict[str, Pose]) -> CalibrationResult:
    missing = [s.key for s in STEPS if s.key not in poses]
    if missing:
        raise ValueError(f"missing calibration poses: {', '.join(missing)}")
    p = poses
    warnings: list[str] = []

    # Yaw: centre the neutral point between the two screen edges so a camera
    # mounted off to one side still gives symmetric limits.
    c = p["center"].yaw
    left, right = p["screen_left"].yaw - c, p["screen_right"].yaw - c
    mid = c + (left + right) / 2 if left * right < 0 else c
    edge_yaw = max(abs(p["screen_left"].yaw - mid), abs(p["screen_right"].yaw - mid))
    away_yaw = min(abs(p["away_left"].yaw - mid), abs(p["away_right"].yaw - mid))
    yaw_thr = _boundary(edge_yaw, away_yaw, "Left/right", warnings)

    # Pitch: positive = looking down.
    cp = p["center"].pitch
    edge_up = max(0.0, cp - p["screen_top"].pitch)
    away_up = cp - p["away_up"].pitch
    up_thr = _boundary(edge_up, away_up, "Up", warnings)

    edge_down = max(0.0, p["screen_bottom"].pitch - cp)
    away_down = p["away_down"].pitch - cp
    down_thr = _boundary(edge_down, away_down, "Down", warnings)

    # Eyes: on-screen glances vs. an eyes-only look past the screen.
    edge_eye = max(p[k].eye for k in ("center", "screen_left", "screen_right", "screen_top", "screen_bottom"))
    away_eye = p["eyes_away"].eye
    if away_eye < edge_eye + 0.1:
        warnings.append("Eyes-only glance was hard to tell apart from looking at the screen; "
                        "eye tracking uses a cautious default.")
        eye_thr = edge_eye + 0.2
    else:
        eye_thr = edge_eye + 0.5 * (away_eye - edge_eye)

    return CalibrationResult(
        yaw_offset=_clamp(mid, -60, 60),
        pitch_offset=_clamp(cp, -60, 60),
        yaw_threshold=_clamp(yaw_thr, 6, 70),
        pitch_up_threshold=_clamp(up_thr, 6, 70),
        pitch_down_threshold=_clamp(down_thr, 6, 70),
        eye_gaze_threshold=round(max(0.3, min(0.95, eye_thr)), 2),
        warnings=warnings,
    )
