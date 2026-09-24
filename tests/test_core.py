import math

import numpy as np
import pytest

from umbra import config
from umbra.gaze import (
    AttentionStateMachine,
    FaceObservation,
    Thresholds,
    decide,
    eye_horizontal,
    head_angles,
)


def rot_y(deg):
    a = math.radians(deg)
    m = np.eye(4)
    m[:3, :3] = [[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]]
    return m


def rot_x(deg):
    a = math.radians(deg)
    m = np.eye(4)
    m[:3, :3] = [[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]]
    return m


# ------------------------------------------------------------------ head pose
def test_identity_is_straight_ahead():
    assert head_angles(np.eye(4)) == pytest.approx((0.0, 0.0))


@pytest.mark.parametrize("deg", [-40, -10, 15, 35])
def test_yaw_recovered(deg):
    yaw, pitch = head_angles(rot_y(deg))
    assert yaw == pytest.approx(deg)
    assert pitch == pytest.approx(0.0, abs=1e-9)


def test_looking_down_is_positive_pitch():
    # Rotating the +Z facing vector toward -Y (down, since +Y is up).
    yaw, pitch = head_angles(rot_x(20))
    assert pitch == pytest.approx(20)
    assert yaw == pytest.approx(0.0, abs=1e-9)


def test_translation_is_ignored():
    m = rot_y(12)
    m[:3, 3] = [5, -3, -40]
    assert head_angles(m)[0] == pytest.approx(12)


def test_eye_horizontal_sign_and_magnitude():
    left = {"eyeLookOutLeft": 0.8, "eyeLookInRight": 0.8}
    right = {"eyeLookInLeft": 0.8, "eyeLookOutRight": 0.8}
    assert eye_horizontal(left) == pytest.approx(0.8)
    assert eye_horizontal(right) == pytest.approx(-0.8)
    assert eye_horizontal({}) == 0.0


# ------------------------------------------------------------------ decisions
def face(yaw=0.0, pitch=0.0, eye=0.0, width=0.3):
    return FaceObservation(yaw, pitch, eye, width)


def test_focused_when_centred():
    assert decide([face()], Thresholds()).looking


def test_head_turn_and_pitch_limits():
    t = Thresholds(yaw=25, pitch_up=20, pitch_down=30)
    assert not decide([face(yaw=30)], t).looking
    assert not decide([face(yaw=-30)], t).looking
    assert decide([face(pitch=25)], t).looking          # within lenient down limit
    assert not decide([face(pitch=35)], t).looking
    assert not decide([face(pitch=-25)], t).looking


def test_calibration_offsets_are_applied():
    t = Thresholds(yaw=25, pitch_down=30, yaw_offset=20, pitch_offset=15)
    assert decide([face(yaw=40, pitch=40)], t).looking
    assert not decide([face(yaw=-10)], t).looking


def test_eye_gaze_toggle():
    assert not decide([face(eye=0.8)], Thresholds(eye=0.6)).looking
    assert decide([face(eye=0.8)], Thresholds(eye=0.6, use_eye_gaze=False)).looking


def test_no_face_behaviour():
    assert not decide([], Thresholds(blur_when_no_face=True)).looking
    assert decide([], Thresholds(blur_when_no_face=False)).looking


def test_extra_face_uses_largest_as_user():
    faces = [face(width=0.1, yaw=60), face(width=0.3)]
    assert decide(faces, Thresholds()).looking  # small distant face ignored
    t = Thresholds(blur_on_extra_face=True)
    assert decide(faces, t).looking  # second face too small to count
    assert not decide([face(width=0.3), face(width=0.25)], t).looking


# ------------------------------------------------------------------ debouncing
def test_state_machine_debounces():
    m = AttentionStateMachine(away_delay=0.7, return_delay=0.15)
    assert m.update(False, 0.0) is True
    assert m.update(False, 0.5) is True
    assert m.update(True, 0.6) is True      # glance back resets the timer
    assert m.update(False, 0.7) is True
    assert m.update(False, 1.41) is False   # 0.71 s sustained -> away
    assert m.update(True, 1.5) is False
    assert m.update(True, 1.66) is True     # quick return


# ------------------------------------------------------------------ config
def test_config_roundtrip_and_validation(tmp_path):
    path = tmp_path / "settings.json"
    s = config.Settings(hotkey="Ctrl+Alt+B", yaw_threshold=500, mode="nonsense", dim=-4)
    config.save(s, path)
    loaded = config.load(path)
    assert loaded.hotkey == "Ctrl+Alt+B"
    assert loaded.yaw_threshold == 80.0
    assert loaded.mode == "blur"
    assert loaded.dim == 0


def test_config_tolerates_garbage(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    assert config.load(path) == config.Settings()
    path.write_text('{"process_fps": "fast", "blur_strength": 70, "unknown": 1}', encoding="utf-8")
    loaded = config.load(path)
    assert loaded.process_fps == config.Settings().process_fps
    assert loaded.blur_strength == 70
