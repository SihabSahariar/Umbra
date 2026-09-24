"""Options window opened from the system tray."""

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QKeySequence
from PyQt5.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import APP_NAME, __version__
from .config import FIT_MODES, MODE_LABELS, MODES, Settings
from .hotkey import HotkeyError, parse_hotkey
from .icons import app_icon

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All files (*)"
MEDIA_FILTER = "GIF / video (*.gif *.mp4 *.avi *.mov *.mkv *.webm *.wmv);;All files (*)"
TEST_OVERLAY_MS = 3000


class HotkeyEdit(QWidget):
    """Captures a single key combination."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.edit = QKeySequenceEdit()
        self.edit.keySequenceChanged.connect(self._trim)
        clear = QPushButton("Clear")
        clear.clicked.connect(self.edit.clear)
        reset = QPushButton("Default (F8)")
        reset.clicked.connect(lambda: self.set_text("F8"))
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.edit, 1)
        row.addWidget(clear)
        row.addWidget(reset)

    def _trim(self, seq: QKeySequence):
        if seq.count() > 1:
            self.edit.setKeySequence(QKeySequence(seq[0]))

    def set_text(self, text: str):
        self.edit.setKeySequence(QKeySequence.fromString(text, QKeySequence.PortableText))

    def text(self) -> str:
        return self.edit.keySequence().toString(QKeySequence.PortableText)


def _slider(lo, hi, value, suffix="", scale=1):
    slider = QSlider(Qt.Horizontal)
    slider.setRange(lo, hi)
    slider.setValue(int(value))
    label = QLabel()
    label.setMinimumWidth(56)
    label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def show(v):
        label.setText(f"{v / scale:g}{suffix}")

    slider.valueChanged.connect(show)
    show(slider.value())
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(slider, 1)
    row.addWidget(label)
    return slider, box


def _file_row(line: QLineEdit, title: str, flt: str, parent):
    browse = QPushButton("Browse…")

    def pick():
        path, _ = QFileDialog.getOpenFileName(parent, title, line.text(), flt)
        if path:
            line.setText(path)

    browse.clicked.connect(pick)
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(line, 1)
    row.addWidget(browse)
    return box


class SettingsDialog(QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle(f"{APP_NAME} settings")
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(560)
        s = controller.settings

        tabs = QTabWidget()
        tabs.addTab(self._general_tab(s), "General")
        tabs.addTab(self._detection_tab(s), "Detection")
        tabs.addTab(self._appearance_tab(s), "Appearance")

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply | QDialogButtonBox.RestoreDefaults
        )
        buttons.accepted.connect(self._ok)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self._apply)
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._restore_defaults)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        footer = QLabel(f"{APP_NAME} {__version__} · video is processed locally and never stored or sent anywhere.")
        footer.setStyleSheet("color:#7a828c;")
        layout.addWidget(footer)
        layout.addWidget(buttons)

        # Our own global hotkey would swallow keys while the user records a new one.
        controller.suspend_hotkey(True)
        self._on_mode_changed()

    # ------------------------------------------------------------------ tabs
    def _general_tab(self, s: Settings):
        w = QWidget()
        form = QFormLayout(w)
        self.enabled = QCheckBox("Protect my screen when I look away")
        self.enabled.setChecked(s.enabled)
        self.autostart = QCheckBox(f"Start {APP_NAME} when I sign in to Windows")
        self.autostart.setChecked(s.autostart)
        self.notifications = QCheckBox("Show tray notifications")
        self.notifications.setChecked(s.notifications)
        self.hotkey = HotkeyEdit()
        self.hotkey.set_text(s.hotkey)
        self.camera = QSpinBox()
        self.camera.setRange(0, 16)
        self.camera.setValue(s.camera_index)
        self.camera.setToolTip("0 is the default webcam. Try 1, 2… for external cameras.")

        form.addRow(self.enabled)
        form.addRow(self.autostart)
        form.addRow(self.notifications)
        form.addRow("Enable / disable hotkey:", self.hotkey)
        form.addRow("Camera:", self.camera)
        hint = QLabel(
            f"The hotkey works system-wide, so other apps won't receive it while {APP_NAME} is running."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#7a828c;")
        form.addRow(hint)
        return w

    def _detection_tab(self, s: Settings):
        w = QWidget()
        outer = QVBoxLayout(w)

        sens = QGroupBox("How far you can look away before the screen blurs")
        form = QFormLayout(sens)
        self.yaw, box = _slider(5, 70, s.yaw_threshold, "°")
        form.addRow("Turn left / right:", box)
        self.pitch_up, box = _slider(5, 70, s.pitch_up_threshold, "°")
        form.addRow("Look up:", box)
        self.pitch_down, box = _slider(5, 70, s.pitch_down_threshold, "°")
        form.addRow("Look down:", box)
        self.use_eyes = QCheckBox("Also track eye direction (sideways glances)")
        self.use_eyes.setChecked(s.use_eye_gaze)
        form.addRow(self.use_eyes)
        self.eye, box = _slider(20, 100, s.eye_gaze_threshold * 100, "", scale=100)
        form.addRow("Eye sensitivity:", box)
        self.use_eyes.toggled.connect(box.setEnabled)
        box.setEnabled(s.use_eye_gaze)
        outer.addWidget(sens)

        timing = QGroupBox("Behaviour")
        form = QFormLayout(timing)
        self.away_delay = QSpinBox()
        self.away_delay.setRange(0, 10000)
        self.away_delay.setSingleStep(100)
        self.away_delay.setSuffix(" ms")
        self.away_delay.setValue(s.away_delay_ms)
        self.return_delay = QSpinBox()
        self.return_delay.setRange(0, 5000)
        self.return_delay.setSingleStep(50)
        self.return_delay.setSuffix(" ms")
        self.return_delay.setValue(s.return_delay_ms)
        self.no_face = QCheckBox("Blur when nobody is in front of the camera")
        self.no_face.setChecked(s.blur_when_no_face)
        self.extra_face = QCheckBox("Blur when someone else is looking at my screen")
        self.extra_face.setChecked(s.blur_on_extra_face)
        self.fps = QSpinBox()
        self.fps.setRange(5, 30)
        self.fps.setSuffix(" fps")
        self.fps.setValue(s.process_fps)
        self.fps.setToolTip("Lower values use less CPU but react more slowly.")
        form.addRow("Blur after looking away for:", self.away_delay)
        form.addRow("Unblur after looking back for:", self.return_delay)
        form.addRow(self.no_face)
        form.addRow(self.extra_face)
        form.addRow("Analysis rate:", self.fps)
        outer.addWidget(timing)

        row = QHBoxLayout()
        calibrate = QPushButton("Run calibration…")
        calibrate.setToolTip("Guided setup that measures your screen edges and look-away poses.")
        calibrate.clicked.connect(self.controller.open_calibration)
        preview = QPushButton("Camera preview…")
        preview.clicked.connect(self.controller.open_preview)
        row.addWidget(calibrate)
        row.addWidget(preview)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)
        return w

    def _appearance_tab(self, s: Settings):
        w = QWidget()
        form = QFormLayout(w)
        self.mode = QComboBox()
        for m in MODES:
            self.mode.addItem(MODE_LABELS[m], m)
        self.mode.setCurrentIndex(MODES.index(s.mode))
        self.mode.currentIndexChanged.connect(self._on_mode_changed)
        form.addRow("When I look away show:", self.mode)

        self.blur_strength, self.blur_box = _slider(1, 100, s.blur_strength)
        form.addRow("Blur strength:", self.blur_box)
        self.live_blur = QCheckBox("Live blur (keeps updating what's behind it)")
        self.live_blur.setChecked(s.live_blur)
        form.addRow(self.live_blur)

        self.image_path = QLineEdit(s.image_path)
        self.image_box = _file_row(self.image_path, "Choose image", IMAGE_FILTER, self)
        form.addRow("Image:", self.image_box)
        self.media_path = QLineEdit(s.media_path)
        self.media_box = _file_row(self.media_path, "Choose GIF or video", MEDIA_FILTER, self)
        form.addRow("GIF / video:", self.media_box)
        self.fit = QComboBox()
        for f in FIT_MODES:
            self.fit.addItem(f.capitalize(), f)
        self.fit.setCurrentIndex(FIT_MODES.index(s.media_fit))
        form.addRow("Scaling:", self.fit)

        self._color = QColor(s.color)
        self.color_btn = QPushButton()
        self.color_btn.clicked.connect(self._pick_color)
        self._paint_color_btn()
        form.addRow("Background color:", self.color_btn)

        self.dim, box = _slider(0, 90, s.dim, "%")
        form.addRow("Darken:", box)
        self.show_message = QCheckBox("Show a message")
        self.show_message.setChecked(s.show_message)
        self.message = QLineEdit(s.message)
        self.show_message.toggled.connect(self.message.setEnabled)
        self.message.setEnabled(s.show_message)
        form.addRow(self.show_message, self.message)
        self.fade = QSpinBox()
        self.fade.setRange(0, 2000)
        self.fade.setSingleStep(20)
        self.fade.setSuffix(" ms")
        self.fade.setValue(s.fade_ms)
        form.addRow("Fade duration:", self.fade)

        test = QPushButton("Test overlay (3 s)")
        test.clicked.connect(self._test_overlay)
        form.addRow(test)
        self._form = form
        return w

    # ------------------------------------------------------------------ helpers
    def _on_mode_changed(self, *_):
        mode = self.mode.currentData()
        for widget, visible in (
            (self.blur_box, mode == "blur"),
            (self.live_blur, mode == "blur"),
            (self.image_box, mode == "image"),
            (self.media_box, mode == "media"),
            (self.fit, mode in ("image", "media")),
        ):
            widget.setVisible(visible)
            label = self._form.labelForField(widget)
            if label is not None:
                label.setVisible(visible)

    def _pick_color(self):
        color = QColorDialog.getColor(self._color, self, "Background color")
        if color.isValid():
            self._color = color
            self._paint_color_btn()

    def _paint_color_btn(self):
        self.color_btn.setText(self._color.name())
        text = "#000" if self._color.lightness() > 140 else "#fff"
        self.color_btn.setStyleSheet(f"background:{self._color.name()};color:{text};padding:4px 14px;")

    def collect(self) -> Settings:
        s = self.controller.settings.copy()
        s.enabled = self.enabled.isChecked()
        s.autostart = self.autostart.isChecked()
        s.notifications = self.notifications.isChecked()
        s.hotkey = self.hotkey.text()
        s.camera_index = self.camera.value()
        s.yaw_threshold = float(self.yaw.value())
        s.pitch_up_threshold = float(self.pitch_up.value())
        s.pitch_down_threshold = float(self.pitch_down.value())
        s.use_eye_gaze = self.use_eyes.isChecked()
        s.eye_gaze_threshold = self.eye.value() / 100
        s.away_delay_ms = self.away_delay.value()
        s.return_delay_ms = self.return_delay.value()
        s.blur_when_no_face = self.no_face.isChecked()
        s.blur_on_extra_face = self.extra_face.isChecked()
        s.process_fps = self.fps.value()
        s.mode = self.mode.currentData()
        s.blur_strength = self.blur_strength.value()
        s.live_blur = self.live_blur.isChecked()
        s.image_path = self.image_path.text().strip()
        s.media_path = self.media_path.text().strip()
        s.media_fit = self.fit.currentData()
        s.color = self._color.name()
        s.dim = self.dim.value()
        s.show_message = self.show_message.isChecked()
        s.message = self.message.text()
        s.fade_ms = self.fade.value()
        return s.validated()

    def _validate(self, s: Settings) -> bool:
        if s.hotkey:
            try:
                parse_hotkey(s.hotkey)
            except HotkeyError as exc:
                QMessageBox.warning(self, APP_NAME, str(exc))
                return False
        if s.mode == "image" and not s.image_path:
            QMessageBox.warning(self, APP_NAME, "Choose an image file, or pick another display mode.")
            return False
        if s.mode == "media" and not s.media_path:
            QMessageBox.warning(self, APP_NAME, "Choose a GIF or video file, or pick another display mode.")
            return False
        return True

    def _apply(self) -> bool:
        s = self.collect()
        if not self._validate(s):
            return False
        return self.controller.apply_settings(s, parent=self)

    def _ok(self):
        if self._apply():
            self.accept()

    def _restore_defaults(self):
        if QMessageBox.question(self, APP_NAME, "Restore all settings to their defaults?") != QMessageBox.Yes:
            return
        defaults = Settings(first_run=False)
        self.controller.apply_settings(defaults, parent=self)
        self.close()
        QTimer.singleShot(0, self.controller.open_settings)

    def _test_overlay(self):
        self.controller.test_overlay(self.collect(), TEST_OVERLAY_MS)

    def done(self, result):
        self.controller.suspend_hotkey(False)
        super().done(result)
