import pytest

from umbra.calibration import STEPS, Pose, compute, summarize
from umbra.config import Settings
from umbra.gaze import FaceObservation, decide
from umbra.tracker import thresholds_from_settings


def poses(**overrides):
    base = {
        "center": Pose(0, 10, 0.05),
        "screen_left": Pose(-12, 10, 0.20),
        "screen_right": Pose(12, 10, 0.20),
        "screen_top": Pose(0, 2, 0.05),
        "screen_bottom": Pose(0, 22, 0.05),
        "away_left": Pose(-50, 10, 0.1),
        "away_right": Pose(50, 10, 0.1),
        "away_up": Pose(0, -20, 0.05),
        "away_down": Pose(0, 50, 0.05),
        "eyes_away": Pose(0, 10, 0.80),
    }
    base.update(overrides)
    return base


def test_summarize_uses_median_and_needs_samples():
    assert summarize([(0, 0, 0)] * 4) is None
    pose = summarize([(1, 2, -0.3)] * 9 + [(90, 90, 1.0)])  # one outlier
    assert (pose.yaw, pose.pitch, pose.eye) == pytest.approx((1, 2, 0.3))


def test_thresholds_sit_between_edges_and_away_poses():
    r = compute(poses())
    assert not r.warnings
    assert r.pitch_offset == 10
    assert 12 < r.yaw_threshold < 50
    assert 8 < r.pitch_up_threshold < 30          # top edge is 8° up, away is 30° up
    assert 12 < r.pitch_down_threshold < 40       # bottom edge 12° down, away 40° down
    assert 0.2 < r.eye_gaze_threshold < 0.8


def test_calibrated_settings_classify_the_recorded_poses():
    p = poses()
    s = Settings()
    compute(p).apply_to(s)
    t = thresholds_from_settings(s)
    for step in STEPS:
        pose = p[step.key]
        looking = decide([FaceObservation(pose.yaw, pose.pitch, pose.eye, 0.3)], t).looking
        assert looking == step.on_screen, step.key


def test_off_centre_camera_recentres_between_screen_edges():
    # Camera to the user's side: screen spans yaw 5..45 with the centre look at 25.
    p = poses(center=Pose(25, 10, 0.05), screen_left=Pose(5, 10, 0.2), screen_right=Pose(45, 10, 0.2),
              away_left=Pose(-30, 10, 0.1), away_right=Pose(80, 10, 0.1))
    r = compute(p)
    assert r.yaw_offset == 25
    assert 20 < r.yaw_threshold < 55


def test_indistinct_away_pose_falls_back_with_warning():
    r = compute(poses(away_left=Pose(-14, 10, 0.1)))
    assert r.warnings and "Left/right" in r.warnings[0]
    assert r.yaw_threshold == pytest.approx(22)  # edge 12 + default margin 10


def test_missing_steps_rejected():
    p = poses()
    del p["away_up"]
    with pytest.raises(ValueError):
        compute(p)
