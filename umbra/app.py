"""Application controller: owns the tray, tracker, overlays and hotkey."""

import logging
from datetime import datetime, timedelta

from PyQt5.QtCore import QObject, QTimer
from PyQt5.QtWidgets import QAction, QActionGroup, QFileDialog, QMenu, QMessageBox, QSystemTrayIcon

from . import APP_NAME, autostart, brand, config
from .config import MODE_LABELS, MODES
from .hotkey import GlobalHotkey, HotkeyError
from .icons import app_icon, state_icon
from .overlay import OverlayManager
from .settings_dialog import IMAGE_FILTER, MEDIA_FILTER, SettingsDialog
from .tracker import FaceTracker

log = logging.getLogger(__name__)

SNOOZE_OPTIONS = ((5, "5 minutes"), (15, "15 minutes"), (30, "30 minutes"), (60, "1 hour"))


class Controller(QObject):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.settings = config.load()
        self.tracker: FaceTracker | None = None
        self.focused = True
        self.status = ("stopped", "")
        self._preview_users = 0
        self._overlay_suspended = False
        self._testing = False
        self._hotkey_suspended = False
        self._settings_dialog = None
        self._preview_dialog = None
        self._wizard = None
        self._about_dialog = None
        self._snooze_until: datetime | None = None

        self.overlay = OverlayManager(self.settings, self)
        self.hotkey = GlobalHotkey(self)
        self.hotkey.activated.connect(self.toggle)
        self._snooze_timer = QTimer(self, singleShot=True, timeout=self._end_snooze)
        self._test_timer = QTimer(self, singleShot=True, timeout=self._end_test_overlay)

        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.activated.connect(self._on_tray_activated)
        self._build_menu()

        # Swap between the light and dark tray mark when the taskbar theme changes.
        self._light_taskbar = brand.taskbar_is_light()
        self._theme_timer = QTimer(self, interval=10_000, timeout=self._check_theme)
        self._theme_timer.start()

    # ================================================================ lifecycle
    def start(self, background: bool = False) -> None:
        self._register_hotkey(self.settings.hotkey, notify=True)
        if self.settings.first_run and autostart.is_enabled():
            # The installer's "Start with Windows" option created the entry; keep it.
            self.settings.autostart = True
        self._sync_autostart()
        self.tray.show()
        if self.settings.enabled:
            self._ensure_tracker()
        self._refresh_ui()

        if self.settings.first_run:
            self.settings.first_run = False
            self._save()
            self.notify(
                f"{APP_NAME} is running",
                f"Your screen blurs when you look away. Press {self.settings.hotkey or 'the tray menu'} "
                "to turn protection on or off.",
            )
        if not self.settings.calibrated:
            if background:
                self.notify(f"{APP_NAME} needs calibration",
                            "Right-click the tray icon and choose Calibrate… for reliable detection.")
            else:
                QTimer.singleShot(600, self.open_calibration)

    def quit(self) -> None:
        log.info("Quitting")
        self._stop_tracker()
        self.overlay.hide()
        self.hotkey.unregister()
        self.tray.hide()
        self.app.quit()

    # ================================================================ tracker
    def _ensure_tracker(self) -> FaceTracker:
        if self.tracker is None or not self.tracker.isRunning():
            self.tracker = FaceTracker(self.settings, self)
            self.tracker.attentionChanged.connect(self._on_attention)
            self.tracker.statusChanged.connect(self._on_status)
            self.tracker.set_preview(self._preview_users > 0)
            self.tracker.start()
            log.info("Tracker started")
        return self.tracker

    def _stop_tracker(self) -> None:
        if self.tracker is not None:
            self.tracker.stop()
            self.tracker.deleteLater()
            self.tracker = None
            log.info("Tracker stopped")
        self.focused = True
        self.status = ("stopped", "")

    def _need_tracker(self) -> bool:
        return self.settings.enabled or self._preview_users > 0

    def _on_attention(self, focused: bool) -> None:
        log.info("Attention: %s", "focused" if focused else "away")
        self.focused = focused
        self._update_overlay()
        self._refresh_ui()

    def _on_status(self, state: str, detail: str) -> None:
        previous = self.status[0]
        self.status = (state, detail)
        log.info("Tracker status: %s - %s", state, detail)
        if state != previous and state in ("error", "no_camera"):
            self.notify(f"{APP_NAME}: camera problem", detail, QSystemTrayIcon.Warning)
            self.focused = True
            self._update_overlay()
        self._refresh_ui()

    # ================================================================ overlay
    def _update_overlay(self) -> None:
        if self._testing:
            return
        show = self.settings.enabled and not self.focused and not self._overlay_suspended
        if show:
            self.overlay.show()
        else:
            self.overlay.hide()

    def suspend_overlay(self, suspended: bool) -> None:
        self._overlay_suspended = suspended
        self._update_overlay()

    def test_overlay(self, settings, ms: int) -> None:
        self._testing = True
        self.overlay.hide()
        self.overlay.apply_settings(settings)
        self.overlay.show()
        self._test_timer.start(ms)

    def _end_test_overlay(self) -> None:
        self.overlay.hide()
        self.overlay.apply_settings(self.settings)
        self._testing = False
        self._update_overlay()

    # ================================================================ enable / snooze
    def toggle(self) -> None:
        self.set_enabled(not self.settings.enabled)
        if self.settings.enabled:
            self.notify(APP_NAME, "Protection enabled")
        else:
            self.notify(APP_NAME, "Protection disabled")

    def set_enabled(self, enabled: bool, persist: bool = True) -> None:
        if persist:
            self._cancel_snooze()
        self.settings.enabled = enabled
        if persist:
            self._save()
        if enabled:
            self._ensure_tracker()
        elif not self._need_tracker():
            self._stop_tracker()
        self._update_overlay()
        self._refresh_ui()

    def snooze(self, minutes: int) -> None:
        self.set_enabled(False, persist=False)
        self._snooze_until = datetime.now() + timedelta(minutes=minutes)
        self._snooze_timer.start(minutes * 60 * 1000)
        self.notify(APP_NAME, f"Paused until {self._snooze_until:%H:%M}")
        self._refresh_ui()

    def _end_snooze(self) -> None:
        self._snooze_until = None
        self.set_enabled(True)
        self.notify(APP_NAME, "Protection resumed")

    def _cancel_snooze(self) -> None:
        self._snooze_timer.stop()
        self._snooze_until = None

    # ================================================================ settings
    def _save(self) -> None:
        """Persist settings; a temporary snooze is never written as 'disabled'."""
        s = self.settings
        if self._snooze_until is not None:
            s = s.copy()
            s.enabled = True
        config.save(s)

    def apply_settings(self, new, parent=None) -> bool:
        old = self.settings
        if new.hotkey != self.hotkey.current or not new.hotkey:
            try:
                self.hotkey.register(new.hotkey)
            except HotkeyError as exc:
                QMessageBox.warning(parent, APP_NAME, f"Could not use that hotkey: {exc}")
                if not self._hotkey_suspended:
                    self._register_hotkey(old.hotkey, notify=False)
                return False
            if self._hotkey_suspended:
                self.hotkey.unregister()

        self.settings = new.validated()
        try:
            self._save()
        except OSError as exc:
            log.exception("Saving settings failed")
            QMessageBox.warning(parent, APP_NAME, f"Settings could not be saved: {exc}")
        if new.autostart != old.autostart or new.autostart != autostart.is_enabled():
            self._sync_autostart(parent)

        if self.tracker is not None:
            self.tracker.update_settings(self.settings)
        if not self._testing:
            self.overlay.apply_settings(self.settings)
        if new.enabled != old.enabled:
            self._cancel_snooze()
            self.set_enabled(new.enabled)
        self._refresh_ui()
        return True

    def save_calibration(self, yaw: float, pitch: float) -> None:
        self.settings.yaw_offset = yaw
        self.settings.pitch_offset = pitch
        self._save()
        if self.tracker is not None:
            self.tracker.update_settings(self.settings)
        log.info("Calibration saved: yaw %.1f pitch %.1f", yaw, pitch)

    def _sync_autostart(self, parent=None) -> None:
        try:
            autostart.set_enabled(self.settings.autostart)
        except OSError as exc:
            log.exception("Autostart update failed")
            QMessageBox.warning(parent, APP_NAME, f"Could not update start-up setting: {exc}")

    def _register_hotkey(self, text: str, notify: bool) -> None:
        try:
            self.hotkey.register(text)
        except HotkeyError as exc:
            log.warning("Hotkey registration failed: %s", exc)
            if notify:
                self.notify(f"{APP_NAME}: hotkey unavailable", f"{exc}. Choose another in Settings.",
                            QSystemTrayIcon.Warning)

    def suspend_hotkey(self, suspended: bool) -> None:
        self._hotkey_suspended = suspended
        if suspended:
            self.hotkey.unregister()
        else:
            self._register_hotkey(self.settings.hotkey, notify=False)

    # ================================================================ windows
    def open_settings(self) -> None:
        if self._settings_dialog is not None and self._settings_dialog.isVisible():
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            return
        self._settings_dialog = SettingsDialog(self)
        self._settings_dialog.finished.connect(lambda _: setattr(self, "_settings_dialog", None))
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def open_about(self) -> None:
        from .about_dialog import AboutDialog

        if self._about_dialog is None:
            self._about_dialog = AboutDialog()
            self._about_dialog.finished.connect(lambda _: setattr(self, "_about_dialog", None))
        self._about_dialog.show()
        self._about_dialog.raise_()
        self._about_dialog.activateWindow()

    def open_preview(self) -> None:
        from .preview import PreviewDialog

        if self._preview_dialog is not None and self._preview_dialog.isVisible():
            self._preview_dialog.raise_()
            self._preview_dialog.activateWindow()
            return
        self._preview_dialog = PreviewDialog(self, self._settings_dialog)
        self._preview_dialog.show()
        self._preview_dialog.raise_()
        self._preview_dialog.activateWindow()

    def open_calibration(self) -> None:
        from .calibration_wizard import CalibrationWizard

        if self._wizard is not None:
            self._wizard.raise_()
            self._wizard.activateWindow()
            return
        if self._preview_dialog is not None and self._preview_dialog.isVisible():
            self._preview_dialog.close()
        if self._settings_dialog is not None and self._settings_dialog.isVisible():
            # Its sliders would overwrite the new limits if it were applied afterwards.
            self._settings_dialog.reject()
        self._wizard = CalibrationWizard(self)
        self._wizard.closed.connect(lambda _: setattr(self, "_wizard", None))
        self._wizard.begin()

    def acquire_tracker_for_preview(self) -> FaceTracker:
        self._preview_users += 1
        tracker = self._ensure_tracker()
        tracker.set_preview(True)
        return tracker

    def release_tracker_for_preview(self, *slots) -> None:
        self._preview_users = max(0, self._preview_users - 1)
        self._overlay_suspended = False
        if self.tracker is not None:
            self.tracker.set_preview(self._preview_users > 0)
            for slot in slots:
                for signal in (self.tracker.previewFrame, self.tracker.captureFinished):
                    try:
                        signal.disconnect(slot)
                    except TypeError:
                        pass
        if not self._need_tracker():
            self._stop_tracker()
        self._update_overlay()
        self._refresh_ui()

    # ================================================================ tray
    def _build_menu(self) -> None:
        menu = QMenu()
        self.header = QAction(APP_NAME, menu, enabled=False)
        menu.addAction(self.header)
        menu.addSeparator()

        self.enable_action = QAction("Protection enabled", menu, checkable=True)
        self.enable_action.triggered.connect(lambda checked: self.set_enabled(checked))
        menu.addAction(self.enable_action)

        snooze = menu.addMenu("Pause for")
        for minutes, label in SNOOZE_OPTIONS:
            snooze.addAction(label, lambda m=minutes: self.snooze(m))

        mode_menu = menu.addMenu("When I look away")
        self.mode_group = QActionGroup(mode_menu)
        self.mode_actions = {}
        for mode in MODES:
            act = QAction(MODE_LABELS[mode], mode_menu, checkable=True)
            act.triggered.connect(lambda _, m=mode: self._choose_mode(m))
            self.mode_group.addAction(act)
            mode_menu.addAction(act)
            self.mode_actions[mode] = act

        menu.addSeparator()
        menu.addAction("Calibrate…", self.open_calibration)
        menu.addAction("Camera preview…", self.open_preview)
        menu.addAction("Settings…", self.open_settings)
        menu.addSeparator()
        menu.addAction(f"About {APP_NAME}", self.open_about)
        menu.addAction("Quit", self.quit)
        self.menu = menu
        self.tray.setContextMenu(menu)

    def _choose_mode(self, mode: str) -> None:
        s = self.settings.copy()
        s.mode = mode
        if mode == "image" and not s.image_path:
            path, _ = QFileDialog.getOpenFileName(None, "Choose image", "", IMAGE_FILTER)
            if not path:
                self._refresh_ui()
                return
            s.image_path = path
        if mode == "media" and not s.media_path:
            path, _ = QFileDialog.getOpenFileName(None, "Choose GIF or video", "", MEDIA_FILTER)
            if not path:
                self._refresh_ui()
                return
            s.media_path = path
        self.apply_settings(s)

    def _check_theme(self) -> None:
        light = brand.taskbar_is_light()
        if light != self._light_taskbar:
            self._light_taskbar = light
            self._refresh_ui()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            self.open_settings()

    def _refresh_ui(self) -> None:
        s = self.settings
        state, detail = self.status
        if not s.enabled:
            icon, text = "disabled", "Paused"
            if self._snooze_until:
                text = f"Paused until {self._snooze_until:%H:%M}"
        elif state in ("error", "no_camera"):
            icon, text = "error", detail or "Camera problem"
        elif state == "starting":
            icon, text = "focused", "Starting…"
        elif not self.focused:
            icon, text = "away", "Screen hidden - look back to reveal"
        else:
            icon, text = "focused", "Protecting your screen"

        self.tray.setIcon(state_icon(icon))
        hotkey = f"  [{s.hotkey}]" if s.hotkey else ""
        self.tray.setToolTip(f"{APP_NAME} - {text}")
        self.header.setText(f"{APP_NAME} - {text}")
        self.enable_action.setChecked(s.enabled)
        self.enable_action.setText(f"Protection enabled{hotkey}")
        self.mode_actions[s.mode].setChecked(True)

    def notify(self, title: str, message: str, icon=QSystemTrayIcon.Information) -> None:
        if self.settings.notifications and self.tray.isVisible() and QSystemTrayIcon.supportsMessages():
            self.tray.showMessage(title, message, icon, 3500)
