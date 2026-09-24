"""Background webcam + MediaPipe face tracking thread."""

import logging
import os
import sys
import threading
import time
import urllib.request

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("GLOG_minloglevel", "2")
# MediaPipe imports TensorFlow if it is installed, but only for optional extras.
# Loading TensorFlow after Qt fails with a DLL initialisation error on Windows, so
# make it look absent (MediaPipe handles that) - the packaged app excludes it too.
sys.modules.setdefault("tensorflow", None)

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PyQt5.QtCore import QThread, pyqtSignal  # noqa: E402
from PyQt5.QtGui import QImage  # noqa: E402

from . import paths  # noqa: E402
from .gaze import (  # noqa: E402
    AttentionStateMachine,
    Decision,
    FaceObservation,
    Thresholds,
    decide,
    eye_horizontal,
    head_angles,
)

log = logging.getLogger(__name__)

CAMERA_RETRY_S = 3.0
READ_FAILURES_BEFORE_REOPEN = 30


def thresholds_from_settings(s) -> Thresholds:
    return Thresholds(
        yaw=s.yaw_threshold,
        pitch_up=s.pitch_up_threshold,
        pitch_down=s.pitch_down_threshold,
        eye=s.eye_gaze_threshold,
        use_eye_gaze=s.use_eye_gaze,
        yaw_offset=s.yaw_offset,
        pitch_offset=s.pitch_offset,
        blur_when_no_face=s.blur_when_no_face,
        blur_on_extra_face=s.blur_on_extra_face,
    )


def ensure_model() -> bytes:
    """Return the face landmarker model, downloading it once if not bundled."""
    found = paths.find_model()
    if found is None:
        target = paths.downloaded_model()
        target.parent.mkdir(parents=True, exist_ok=True)
        log.info("Downloading face model to %s", target)
        tmp = target.with_suffix(".part")
        with urllib.request.urlopen(paths.MODEL_URL, timeout=30) as resp, open(tmp, "wb") as fh:
            while chunk := resp.read(65536):
                fh.write(chunk)
        os.replace(tmp, target)
        found = target
    # Loading from a buffer avoids MediaPipe's trouble with non-ASCII paths.
    return found.read_bytes()


class FaceTracker(QThread):
    attentionChanged = pyqtSignal(bool)          # True = focused on screen
    statusChanged = pyqtSignal(str, str)         # (state, human-readable detail)
    metrics = pyqtSignal(object)                 # Decision, ~5 Hz
    previewFrame = pyqtSignal(QImage)
    captureFinished = pyqtSignal(object)         # list of raw (yaw, pitch, eye_h) samples

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._settings = settings.copy()
        self._dirty = True
        self._camera_changed = False
        self._preview = False
        self._calib_until: float | None = None
        self._calib_samples: list[tuple[float, float, float]] = []

    # ---- thread-safe controls (called from the GUI thread) ----
    def update_settings(self, settings) -> None:
        with self._lock:
            camera_changed = settings.camera_index != self._settings.camera_index
            self._settings = settings.copy()
            self._dirty = True
            self._camera_changed = camera_changed

    def set_preview(self, enabled: bool) -> None:
        self._preview = enabled

    def start_capture(self, seconds: float = 1.5) -> None:
        """Record raw, uncalibrated pose samples; result arrives via captureFinished."""
        with self._lock:
            self._calib_samples = []
            self._calib_until = time.monotonic() + seconds

    def stop(self) -> None:
        self._stop.set()
        self.wait(5000)

    # ---- worker ----
    def run(self) -> None:
        try:
            self._run()
        except Exception as exc:  # never let the thread die silently
            log.exception("Tracker crashed")
            self.statusChanged.emit("error", f"Tracking stopped: {exc}")

    def _run(self) -> None:
        from mediapipe import Image, ImageFormat
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import (
            FaceLandmarker,
            FaceLandmarkerOptions,
            RunningMode,
        )

        self.statusChanged.emit("starting", "Loading face modelâ€¦")
        try:
            model = ensure_model()
        except Exception as exc:
            log.exception("Model unavailable")
            self.statusChanged.emit("error", f"Could not load face model: {exc}")
            return

        options = FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_buffer=model),
            running_mode=RunningMode.VIDEO,
            num_faces=2,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
        )

        with FaceLandmarker.create_from_options(options) as landmarker:
            cap = None
            machine = AttentionStateMachine(0.7, 0.15)
            thresholds = Thresholds()
            interval = 1 / 15
            last_process = 0.0
            last_metrics = 0.0
            last_ts = 0
            failures = 0
            reported_focus: bool | None = None

            while not self._stop.is_set():
                with self._lock:
                    if self._dirty:
                        s = self._settings
                        thresholds = thresholds_from_settings(s)
                        machine.away_delay = s.away_delay_ms / 1000
                        machine.return_delay = s.return_delay_ms / 1000
                        interval = 1 / s.process_fps
                        camera_index = s.camera_index
                        self._dirty = False
                    reopen = self._camera_changed
                    self._camera_changed = False

                if reopen and cap is not None:
                    cap.release()
                    cap = None

                if cap is None:
                    cap = self._open_camera(camera_index)
                    if cap is None:
                        if reported_focus is not True:
                            # Never lock the user out when the camera is gone.
                            self.attentionChanged.emit(True)
                            reported_focus = True
                        machine.reset(True)
                        self._stop.wait(CAMERA_RETRY_S)
                        continue
                    failures = 0
                    self.statusChanged.emit("running", "Watching for attention")

                if not cap.grab():
                    failures += 1
                    if failures >= READ_FAILURES_BEFORE_REOPEN:
                        log.warning("Camera stopped delivering frames; reopening")
                        cap.release()
                        cap = None
                    else:
                        self._stop.wait(0.05)
                    continue
                failures = 0

                now = time.monotonic()
                if now - last_process < interval:
                    continue
                last_process = now

                ok, frame = cap.retrieve()
                if not ok or frame is None:
                    continue

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                ts = max(last_ts + 1, int(now * 1000))
                last_ts = ts
                result = landmarker.detect_for_video(
                    Image(image_format=ImageFormat.SRGB, data=np.ascontiguousarray(rgb)), ts
                )

                observations = self._observations(result)
                self._collect_calibration(observations, now)
                decision = decide(observations, thresholds)
                focused = machine.update(decision.looking, now)
                if focused != reported_focus:
                    reported_focus = focused
                    self.attentionChanged.emit(focused)

                if now - last_metrics >= 0.2:
                    last_metrics = now
                    self.metrics.emit(decision)
                if self._preview:
                    self.previewFrame.emit(self._render_preview(frame, result, decision, focused))

            if cap is not None:
                cap.release()
        self.statusChanged.emit("stopped", "Protection paused")

    def _open_camera(self, index: int):
        backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY] if os.name == "nt" else [cv2.CAP_ANY]
        for backend in backends:
            cap = cv2.VideoCapture(index, backend)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                ok, _ = cap.read()
                if ok:
                    log.info("Opened camera %d (backend %d)", index, backend)
                    return cap
            cap.release()
        log.warning("Camera %d unavailable", index)
        self.statusChanged.emit("no_camera", f"Camera {index} is unavailable - retrying")
        return None

    @staticmethod
    def _observations(result) -> list[FaceObservation]:
        out = []
        matrices = result.facial_transformation_matrixes or []
        blend_lists = result.face_blendshapes or []
        for i, landmarks in enumerate(result.face_landmarks or []):
            if i >= len(matrices):
                break
            yaw, pitch = head_angles(matrices[i])
            blend = {}
            if i < len(blend_lists):
                blend = {c.category_name: c.score for c in blend_lists[i]}
            xs = [p.x for p in landmarks]
            out.append(FaceObservation(yaw, pitch, eye_horizontal(blend), max(xs) - min(xs)))
        return out

    def _collect_calibration(self, observations, now: float) -> None:
        with self._lock:
            if self._calib_until is None:
                return
            if observations:
                main = max(observations, key=lambda o: o.width)
                self._calib_samples.append((main.yaw, main.pitch, main.eye_h))
            if now < self._calib_until:
                return
            samples = self._calib_samples
            self._calib_until = None
            self._calib_samples = []
        self.captureFinished.emit(samples)

    @staticmethod
    def _render_preview(frame, result, decision: Decision, focused: bool) -> QImage:
        view = frame.copy()
        h, w = view.shape[:2]
        color = (80, 200, 90) if focused else (60, 90, 240)
        for landmarks in result.face_landmarks or []:
            xs = [int(p.x * w) for p in landmarks]
            ys = [int(p.y * h) for p in landmarks]
            cv2.rectangle(view, (min(xs), min(ys)), (max(xs), max(ys)), color, 2)
            for idx in (1, 33, 263, 61, 291, 468, 473):
                if idx < len(landmarks):
                    cv2.circle(view, (xs[idx], ys[idx]), 2, (255, 255, 255), -1)
        view = cv2.flip(view, 1)  # mirror so it feels like a mirror
        lines = [f"{'FOCUSED' if focused else 'AWAY'}  ({decision.reason})"]
        if decision.yaw is not None:
            lines.append(f"yaw {decision.yaw:+.1f}  pitch {decision.pitch:+.1f}  eyes {decision.eye_h:+.2f}")
        lines.append(f"faces: {decision.faces}")
        for i, text in enumerate(lines):
            y = 28 + i * 26
            cv2.putText(view, text, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 4, cv2.LINE_AA)
            cv2.putText(view, text, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2, cv2.LINE_AA)
        rgb = cv2.cvtColor(view, cv2.COLOR_BGR2RGB)
        return QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
