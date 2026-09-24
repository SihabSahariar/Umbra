"""Full-screen guided calibration wizard."""

import logging

from PyQt5.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPainterPath, QPen, QPixmap
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import APP_NAME, brand
from .calibration import STEPS, compute, summarize
from .icons import app_icon

log = logging.getLogger(__name__)

CAPTURE_SECONDS = 1.5
COUNTDOWN_ON_SCREEN = 2
COUNTDOWN_AWAY = 3
EDGE_MARGIN = 28

# Where to draw the target for each step: (anchor, arrow direction)
TARGETS = {
    "center": ("center", None),
    "screen_left": ("left", "left"),
    "screen_right": ("right", "right"),
    "screen_top": ("top", "up"),
    "screen_bottom": ("bottom", "down"),
    "away_left": ("left", "left"),
    "away_right": ("right", "right"),
    "away_up": ("top", "up"),
    "away_down": ("bottom", "down"),
    "eyes_away": ("left", "left"),
}

PANEL_CSS = """
QWidget#panel { background: rgba(42, 40, 51, 235); border-radius: 18px; }
QLabel { color: #F6F4EF; }
QLabel#step { color: #8a93a0; font-size: 12pt; }
QLabel#title { font-size: 20pt; font-weight: 600; }
QLabel#instruction { font-size: 13pt; color: #c9d0da; }
QLabel#status { font-size: 13pt; font-weight: 600; }
QLabel#video { background: #2A2833; border-radius: 10px; color: #6f7883; }
QPushButton { background: #3a3845; color: #F6F4EF; border: none; border-radius: 8px;
              padding: 9px 18px; font-size: 11pt; }
QPushButton:hover { background: #4a4757; }
QPushButton:disabled { color: #6f7883; }
QPushButton#primary { background: #FFB547; color: #0F0F13; font-weight: 600; }
QPushButton#primary:hover { background: #ffc46e; }
QPushButton#primary:disabled { background: #3a3845; color: #6f6c7a; }
"""


class CalibrationWizard(QWidget):
    closed = pyqtSignal(bool)  # True if new calibration was saved

    def __init__(self, controller):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.controller = controller
        self.setWindowTitle(f"{APP_NAME} calibration")
        self.setWindowIcon(app_icon())
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setStyleSheet(PANEL_CSS)

        self.index = 0
        self.poses = {}
        self.phase = "ready"  # ready | countdown | capturing | done | summary
        self.result = None
        self._saved = False
        self._countdown = 0
        self._have_frames = False
        self._pulse = 0.0
        self._tracker = None

        self._tick_timer = QTimer(self, interval=1000, timeout=self._tick)
        self._pulse_timer = QTimer(self, interval=40, timeout=self._animate)
        self._build_panel()

    # ------------------------------------------------------------------ ui
    def _build_panel(self):
        self.panel = QWidget(self, objectName="panel")
        self.step_label = QLabel(objectName="step")
        self.title = QLabel(objectName="title", wordWrap=True)
        self.instruction = QLabel(objectName="instruction", wordWrap=True)
        self.status = QLabel(objectName="status", wordWrap=True)
        # The camera thumbnail lives in the screen corner, outside the text panel.
        self.video = QLabel("Starting camera…", self, objectName="video", alignment=Qt.AlignCenter)
        self.video.setFixedSize(240, 180)

        self.back_btn = QPushButton("Back")
        self.back_btn.clicked.connect(self._back)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.close)
        self.redo_btn = QPushButton("Redo all")
        self.redo_btn.clicked.connect(self._restart)
        self.primary_btn = QPushButton(objectName="primary")
        self.primary_btn.clicked.connect(self._primary)

        text = QVBoxLayout()
        text.addWidget(self.step_label)
        text.addWidget(self.title)
        text.addWidget(self.instruction)
        text.addSpacing(6)
        text.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.addWidget(self.cancel_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.back_btn)
        buttons.addWidget(self.redo_btn)
        buttons.addWidget(self.primary_btn)

        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.addLayout(text)
        layout.addSpacing(10)
        layout.addLayout(buttons)

    def begin(self):
        screen = QGuiApplication.primaryScreen()
        self.setGeometry(screen.geometry())
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.controller.suspend_overlay(True)
        self._tracker = self.controller.acquire_tracker_for_preview()
        self._tracker.previewFrame.connect(self._on_frame)
        self._tracker.captureFinished.connect(self._on_capture)
        self._tracker.statusChanged.connect(self._on_status)
        self._pulse_timer.start()
        self._show_step(0)

    def resizeEvent(self, event):
        self._layout_panel()
        super().resizeEvent(event)

    def _layout_panel(self):
        """Size the panel to its text and keep it on the side away from the target."""
        w, h = self.width(), self.height()
        self.video.move(w - self.video.width() - 40, h - self.video.height() - 40)
        pw = min(720, w - 2 * 90)
        layout = self.panel.layout()
        layout.activate()
        needed = layout.totalHeightForWidth(pw) if layout.hasHeightForWidth() else layout.sizeHint().height()
        gap = 50
        target_on_top = self.phase != "summary" and TARGETS[self.step.key][0] == "top"
        if target_on_top:
            y = h / 2 + gap
            ph = min(needed, h - y - 20)
        else:
            ph = min(needed, h / 2 - gap - 20)
            y = h / 2 - gap - ph
        self.panel.setGeometry(int((w - pw) / 2), int(y), int(pw), int(ph))

    # ------------------------------------------------------------------ steps
    @property
    def step(self):
        return STEPS[self.index]

    def _show_step(self, index: int):
        self.index = index
        self.phase = "ready"
        step = self.step
        self.step_label.setText(f"Step {index + 1} of {len(STEPS)}" +
                                ("  ·  should stay visible" if step.on_screen else "  ·  should blur"))
        self.title.setText(step.title)
        extra = "" if step.on_screen else " You'll hear a beep when to start and another when you can look back."
        self.instruction.setText(step.instruction + extra)
        self._set_status("Press <b>Space</b> or <b>Start</b> when you're ready." if self._have_frames
                         else "Waiting for the camera…", "#c9d0da")
        self.primary_btn.setText("Start")
        self.back_btn.setVisible(True)
        self.back_btn.setEnabled(index > 0)
        self.redo_btn.setVisible(False)
        self.video.setVisible(True)
        self._update_primary()
        self._layout_panel()
        self.update()

    def _update_primary(self):
        busy = self.phase in ("countdown", "capturing", "done")
        self.primary_btn.setEnabled(self.phase == "summary" or (self._have_frames and not busy))
        self.back_btn.setEnabled(not busy and self.index > 0 and self.phase != "summary")

    def _primary(self):
        if self.phase == "summary":
            self._save()
        elif self.phase == "ready":
            self._start_countdown()

    def _start_countdown(self):
        self.phase = "countdown"
        self._countdown = COUNTDOWN_ON_SCREEN if self.step.on_screen else COUNTDOWN_AWAY
        self._set_status(f"Get ready… {self._countdown}", "#f0c05a")
        self._update_primary()
        self._tick_timer.start()

    def _tick(self):
        self._countdown -= 1
        if self._countdown > 0:
            self._set_status(f"Get ready… {self._countdown}", "#f0c05a")
            return
        self._tick_timer.stop()
        self.phase = "capturing"
        QApplication.beep()
        self._set_status("Hold still… recording", "#5aa9f0")
        self._update_primary()
        self._tracker.start_capture(CAPTURE_SECONDS)
        self.update()

    def _on_capture(self, samples):
        if self.phase != "capturing":
            return
        QApplication.beep()
        pose = summarize(samples)
        if pose is None:
            self.phase = "ready"
            self._set_status("No face was detected. Check the lighting and that the camera can see you, "
                             "then press <b>Space</b> to retry.", "#f06a6a")
            self._update_primary()
            return
        self.poses[self.step.key] = pose
        log.info("Calibration %s: yaw %.1f pitch %.1f eye %.2f", self.step.key, pose.yaw, pose.pitch, pose.eye)
        self.phase = "done"
        self._set_status("Got it ✓  You can look back at the screen.", "#4fd18b")
        self._update_primary()
        QTimer.singleShot(900, self._advance)

    def _advance(self):
        if self.phase != "done":
            return
        if self.index + 1 < len(STEPS):
            self._show_step(self.index + 1)
        else:
            self._show_summary()

    def _back(self):
        if self.index > 0 and self.phase in ("ready", "summary"):
            self._show_step(self.index - 1 if self.phase == "ready" else len(STEPS) - 1)

    def _restart(self):
        self.poses.clear()
        self._show_step(0)

    def _show_summary(self):
        self.phase = "summary"
        self.result = r = compute(self.poses)
        self.step_label.setText("Calibration complete")
        self.title.setText("Your personal detection limits")
        lines = [
            f"Turn left / right: <b>±{r.yaw_threshold:.0f}°</b> &nbsp; "
            f"Look up: <b>{r.pitch_up_threshold:.0f}°</b> &nbsp; Look down: <b>{r.pitch_down_threshold:.0f}°</b>",
            f"Eye sensitivity: <b>{r.eye_gaze_threshold:.2f}</b>",
        ]
        self.instruction.setText("<br>".join(lines))
        if r.warnings:
            self._set_status("<br>".join("⚠ " + w for w in r.warnings), "#f0c05a")
        else:
            self._set_status("Everything looks good. You can fine-tune these later in Settings → Detection.",
                             "#4fd18b")
        self.primary_btn.setText("Save")
        self.back_btn.setVisible(True)
        self.redo_btn.setVisible(True)
        self.video.setVisible(False)
        self._update_primary()
        self.back_btn.setEnabled(True)
        self._layout_panel()
        self.update()

    def _save(self):
        s = self.controller.settings.copy()
        self.result.apply_to(s)
        s.calibrated = True
        if self.controller.apply_settings(s, parent=self):
            self._saved = True
            self.controller.notify(APP_NAME, "Calibration saved. Look away to test it.")
            self.close()

    def _set_status(self, html: str, color: str):
        self.status.setText(html)
        self.status.setStyleSheet(f"color:{color};")
        self._layout_panel()

    # ------------------------------------------------------------------ tracker events
    def _on_frame(self, image: QImage):
        if not self._have_frames:
            self._have_frames = True
            if self.phase == "ready":
                self._set_status("Press <b>Space</b> or <b>Start</b> when you're ready.", "#c9d0da")
            self._update_primary()
        if not self.video.isVisible():
            return
        self.video.setPixmap(QPixmap.fromImage(image).scaled(self.video.size(), Qt.KeepAspectRatio,
                                                             Qt.SmoothTransformation))

    def _on_status(self, state: str, detail: str):
        if state in ("error", "no_camera"):
            self._have_frames = False
            self._set_status(detail, "#f06a6a")
            self._update_primary()

    # ------------------------------------------------------------------ input / lifecycle
    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Escape:
            self.close()
        elif key in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter) and self.primary_btn.isEnabled():
            self._primary()
        elif key == Qt.Key_Backspace:
            self._back()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self._tick_timer.stop()
        self._pulse_timer.stop()
        if self._tracker is not None:
            try:
                self._tracker.statusChanged.disconnect(self._on_status)
            except TypeError:
                pass
            self.controller.release_tracker_for_preview(self._on_frame, self._on_capture)
            self._tracker = None
        self.controller.suspend_overlay(False)
        self.closed.emit(self._saved)
        super().closeEvent(event)

    # ------------------------------------------------------------------ painting
    def _animate(self):
        self._pulse = (self._pulse + 0.04) % 1.0
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(brand.INK))
        if self.phase == "summary":
            return
        step = self.step
        anchor, direction = TARGETS[step.key]
        color = QColor(brand.AMBER) if step.on_screen else QColor(brand.PAPER)
        w, h = self.width(), self.height()
        points = {
            "center": QPointF(w / 2, h / 2 - 40),
            "left": QPointF(EDGE_MARGIN, h / 2 - 40),
            "right": QPointF(w - EDGE_MARGIN, h / 2 - 40),
            "top": QPointF(w / 2, EDGE_MARGIN),
            "bottom": QPointF(w / 2, h - EDGE_MARGIN),
        }
        target = points[anchor]
        if anchor == "center" and step.key == "center":
            target = QPointF(w / 2, h / 2)  # the true centre of the screen

        if step.on_screen:
            self._draw_dot(p, target, color)
            if direction:
                self._draw_arrow(p, target, direction, color, inward=True)
        else:
            self._draw_arrow(p, target, direction, color, inward=False)
            label = "eyes only" if step.key == "eyes_away" else "look away"
            p.setPen(color)
            p.setFont(QFont("Segoe UI", 14, QFont.DemiBold))
            offset = {"left": QPointF(62, 46), "right": QPointF(-62, 46),
                      "up": QPointF(0, 150), "down": QPointF(0, -150)}[direction]
            c = target + offset
            p.drawText(QRectF(c.x() - 90, c.y() - 20, 180, 40), Qt.AlignCenter, label)
        p.end()

    def _draw_dot(self, p: QPainter, c: QPointF, color: QColor):
        active = self.phase in ("countdown", "capturing")
        ring = 14 + 16 * self._pulse
        halo = QColor(color)
        halo.setAlphaF(0.55 * (1 - self._pulse))
        p.setPen(QPen(halo, 3))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, ring, ring)
        p.setPen(Qt.NoPen)
        p.setBrush(color if active else color.darker(115))
        p.drawEllipse(c, 9, 9)
        p.setBrush(QColor(brand.INK))
        p.drawEllipse(c, 3, 3)

    def _draw_arrow(self, p: QPainter, tip: QPointF, direction: str, color: QColor, inward: bool):
        """Arrow pointing `direction`. Inward arrows end just before an edge target."""
        vec = {"left": QPointF(-1, 0), "right": QPointF(1, 0), "up": QPointF(0, -1), "down": QPointF(0, 1)}[direction]
        length, head = 110.0, 26.0
        end = tip - vec * (28 if inward else 0)
        start = end - vec * length
        p.setPen(QPen(color, 7, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(start, end - vec * (head * 0.6))
        perp = QPointF(-vec.y(), vec.x())
        path = QPainterPath(end)
        path.lineTo(end - vec * head + perp * (head * 0.7))
        path.lineTo(end - vec * head - perp * (head * 0.7))
        path.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawPath(path)
