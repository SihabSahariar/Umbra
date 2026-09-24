"""Live camera preview with pose readout, quick re-centring and the full wizard."""

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from . import APP_NAME
from .calibration import summarize
from .icons import app_icon

RECENTER_COUNTDOWN = 3


class PreviewDialog(QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle(f"{APP_NAME} - Camera preview")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(560, 500)

        self.video = QLabel("Starting camera…")
        self.video.setAlignment(Qt.AlignCenter)
        self.video.setMinimumSize(480, 360)
        self.video.setStyleSheet("background:#0f1216;color:#9aa3ad;border-radius:8px;")

        self.info = QLabel(
            "Turn your head and eyes to check when the screen would blur. "
            "<b>Full calibration</b> measures your screen edges and look-away poses; "
            "<b>Re-centre</b> only updates your neutral position (e.g. after moving your chair)."
        )
        self.info.setWordWrap(True)
        self.offsets = QLabel()
        wizard_btn = QPushButton("Full calibration…")
        wizard_btn.clicked.connect(self._open_wizard)
        self.recenter_btn = QPushButton("Re-centre")
        self.recenter_btn.clicked.connect(self._start_recenter)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)

        buttons = QHBoxLayout()
        buttons.addWidget(wizard_btn)
        buttons.addWidget(self.recenter_btn)
        buttons.addStretch(1)
        buttons.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.video, 1)
        layout.addWidget(self.info)
        layout.addWidget(self.offsets)
        layout.addLayout(buttons)

        self._countdown = 0
        self._recentering = False
        self._timer = QTimer(self, interval=1000, timeout=self._tick)
        self._update_offsets()

    # ---- lifecycle ----
    def showEvent(self, event):
        super().showEvent(event)
        tracker = self.controller.acquire_tracker_for_preview()
        tracker.previewFrame.connect(self._on_frame)
        tracker.captureFinished.connect(self._on_capture)

    def closeEvent(self, event):
        self._timer.stop()
        self.controller.release_tracker_for_preview(self._on_frame, self._on_capture)
        super().closeEvent(event)

    def _on_frame(self, image: QImage):
        pm = QPixmap.fromImage(image).scaled(self.video.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.video.setPixmap(pm)

    def _open_wizard(self):
        self.close()
        QTimer.singleShot(0, self.controller.open_calibration)

    # ---- quick re-centre ----
    def _start_recenter(self):
        self.recenter_btn.setEnabled(False)
        self._countdown = RECENTER_COUNTDOWN
        self.controller.suspend_overlay(True)
        self.info.setText(f"<b>Look at the centre of your screen…</b> starting in {self._countdown}")
        self._timer.start()

    def _tick(self):
        self._countdown -= 1
        if self._countdown > 0:
            self.info.setText(f"<b>Look at the centre of your screen…</b> starting in {self._countdown}")
            return
        self._timer.stop()
        self._recentering = True
        self.info.setText("<b>Hold still and keep looking at the centre…</b>")
        self.controller.tracker.start_capture(2.0)

    def _on_capture(self, samples):
        if not self._recentering:
            return
        self._recentering = False
        self.recenter_btn.setEnabled(True)
        self.controller.suspend_overlay(False)
        pose = summarize(samples)
        if pose is not None:
            self.controller.save_calibration(pose.yaw, pose.pitch)
            self.info.setText("<b>Re-centred.</b> Turn your head to test when the screen would blur.")
        else:
            self.info.setText("<b>No face was detected.</b> Check lighting and try again.")
        self._update_offsets()

    def _update_offsets(self):
        s = self.controller.settings
        self.offsets.setText(
            f"Neutral pose: yaw {s.yaw_offset:+.1f}°, pitch {s.pitch_offset:+.1f}°  ·  "
            f"limits: ±{s.yaw_threshold:.0f}° sideways, {s.pitch_up_threshold:.0f}° up, "
            f"{s.pitch_down_threshold:.0f}° down"
        )
