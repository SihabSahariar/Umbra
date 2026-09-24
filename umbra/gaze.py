"""Pure attention logic: head pose maths, per-frame decisions, debouncing.

Kept free of Qt / camera code so it can be unit tested in isolation.
"""

import math
from dataclasses import dataclass

import numpy as np


def head_angles(transform: np.ndarray) -> tuple[float, float]:
    """Return (yaw, pitch) in degrees from a MediaPipe facial transformation matrix.

    MediaPipe's metric space is right-handed with +Y up and the camera looking
    down -Z; the canonical face looks along +Z (toward the camera). We rotate
    that forward vector and read its direction, which avoids Euler-order issues.
    Positive pitch means looking *down*; yaw sign is irrelevant (symmetric).
    """
    m = np.asarray(transform, dtype=np.float64)
    fwd = m[:3, :3] @ np.array([0.0, 0.0, 1.0])
    norm = np.linalg.norm(fwd)
    if norm < 1e-9:
        return 0.0, 0.0
    fx, fy, fz = fwd / norm
    yaw = math.degrees(math.atan2(fx, fz))
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, -fy))))
    return yaw, pitch


def eye_horizontal(blendshapes: dict[str, float]) -> float:
    """Sideways gaze from ARKit-style blendshapes, roughly in [-1, 1]."""
    g = blendshapes.get
    left = g("eyeLookOutLeft", 0.0) - g("eyeLookInLeft", 0.0)
    right = g("eyeLookOutRight", 0.0) - g("eyeLookInRight", 0.0)
    return (left - right) / 2.0


@dataclass
class Thresholds:
    yaw: float = 28.0
    pitch_up: float = 22.0
    pitch_down: float = 32.0
    eye: float = 0.60
    use_eye_gaze: bool = True
    yaw_offset: float = 0.0
    pitch_offset: float = 0.0
    blur_when_no_face: bool = True
    blur_on_extra_face: bool = False


@dataclass
class FaceObservation:
    yaw: float
    pitch: float
    eye_h: float
    width: float  # normalised face width in the frame, used to rank faces


@dataclass
class Decision:
    looking: bool
    reason: str
    yaw: float | None = None
    pitch: float | None = None
    eye_h: float | None = None
    faces: int = 0


def decide(faces: list[FaceObservation], t: Thresholds) -> Decision:
    """Decide whether the user is looking at the screen in a single frame."""
    if not faces:
        return Decision(not t.blur_when_no_face, "no face", faces=0)

    faces = sorted(faces, key=lambda f: f.width, reverse=True)
    main = faces[0]
    yaw = main.yaw - t.yaw_offset
    pitch = main.pitch - t.pitch_offset
    base = dict(yaw=yaw, pitch=pitch, eye_h=main.eye_h, faces=len(faces))

    if t.blur_on_extra_face and len(faces) > 1 and faces[1].width >= 0.45 * main.width:
        return Decision(False, "another person", **base)
    if abs(yaw) > t.yaw:
        return Decision(False, "head turned", **base)
    if pitch > t.pitch_down:
        return Decision(False, "looking down", **base)
    if -pitch > t.pitch_up:
        return Decision(False, "looking up", **base)
    if t.use_eye_gaze and abs(main.eye_h) > t.eye:
        return Decision(False, "eyes away", **base)
    return Decision(True, "focused", **base)


class AttentionStateMachine:
    """Debounces noisy per-frame decisions into a stable focused/away state.

    Going *away* requires sustained evidence (avoids blurring on blinks or quick
    glances); coming *back* uses a separate, typically much shorter, delay.
    """

    def __init__(self, away_delay: float, return_delay: float, focused: bool = True):
        self.away_delay = away_delay
        self.return_delay = return_delay
        self.focused = focused
        self._pending_since: float | None = None

    def reset(self, focused: bool = True) -> None:
        self.focused = focused
        self._pending_since = None

    def update(self, looking: bool, now: float) -> bool:
        if looking == self.focused:
            self._pending_since = None
            return self.focused
        if self._pending_since is None:
            self._pending_since = now
        delay = self.away_delay if self.focused else self.return_delay
        if now - self._pending_since >= delay:
            self.focused = looking
            self._pending_since = None
        return self.focused
