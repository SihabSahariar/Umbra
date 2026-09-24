"""Full-screen privacy overlays (one per monitor) and their backdrops."""

import logging
from pathlib import Path

import cv2
import numpy as np
from PyQt5.QtCore import QObject, QPropertyAnimation, QRectF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QGuiApplication, QImage, QMovie, QPainter, QPixmap
from PyQt5.QtWidgets import QWidget

from . import APP_NAME, brand
from .winutil import exclude_from_capture

log = logging.getLogger(__name__)

LIVE_BLUR_INTERVAL_MS = 450
MAX_VIDEO_WIDTH = 1920


# --------------------------------------------------------------------------- helpers
def qimage_to_array(img: QImage) -> np.ndarray:
    img = img.convertToFormat(QImage.Format_RGB32)
    w, h = img.width(), img.height()
    ptr = img.constBits()
    ptr.setsize(img.byteCount())
    arr = np.frombuffer(ptr, np.uint8).reshape(h, img.bytesPerLine())
    return arr[:, : w * 4].reshape(h, w, 4).copy()


def blur_pixmap(pm: QPixmap, strength: int) -> QPixmap:
    """Heavy, cheap blur: downscale 8x, gaussian blur, let Qt upscale smoothly."""
    arr = qimage_to_array(pm.toImage())
    h, w = arr.shape[:2]
    sw, sh = max(1, w // 8), max(1, h // 8)
    small = cv2.resize(arr, (sw, sh), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), max(0.8, strength * 0.12))
    small = np.ascontiguousarray(small)
    return QPixmap.fromImage(QImage(small.data, sw, sh, sw * 4, QImage.Format_RGB32).copy())


def draw_fitted(p: QPainter, target: QRectF, pm: QPixmap, fit: str) -> None:
    if pm is None or pm.isNull():
        return
    src_w, src_h = pm.width(), pm.height()
    if fit == "stretch":
        p.drawPixmap(target, pm, QRectF(0, 0, src_w, src_h))
        return
    sx, sy = target.width() / src_w, target.height() / src_h
    scale = max(sx, sy) if fit == "cover" else min(sx, sy)
    w, h = src_w * scale, src_h * scale
    dest = QRectF(target.x() + (target.width() - w) / 2, target.y() + (target.height() - h) / 2, w, h)
    p.drawPixmap(dest, pm, QRectF(0, 0, src_w, src_h))


# --------------------------------------------------------------------------- backdrops
class Backdrop(QObject):
    changed = pyqtSignal()

    def start(self, screens, live_capture_ok: bool) -> None: ...
    def stop(self) -> None: ...
    def paint(self, p: QPainter, rect: QRectF, screen) -> None: ...


class ColorBackdrop(Backdrop):
    def __init__(self, color: str):
        super().__init__()
        self.color = QColor(color) if QColor(color).isValid() else QColor(brand.INK)

    def paint(self, p, rect, screen):
        p.fillRect(rect, self.color)


class BlurBackdrop(Backdrop):
    def __init__(self, strength: int, live: bool):
        super().__init__()
        self.strength = strength
        self.live = live
        self._frames: dict[str, QPixmap] = {}
        self._screens = []
        self._timer = QTimer(self)
        self._timer.setInterval(LIVE_BLUR_INTERVAL_MS)
        self._timer.timeout.connect(self._capture)

    def start(self, screens, live_capture_ok):
        self._screens = list(screens)
        self._capture()
        if self.live and live_capture_ok:
            self._timer.start()

    def stop(self):
        self._timer.stop()
        self._frames.clear()  # don't keep screenshots of private content around
        self._screens = []

    def _capture(self):
        for screen in self._screens:
            try:
                shot = screen.grabWindow(0)
                if shot.isNull():
                    continue
                self._frames[screen.name()] = blur_pixmap(shot, self.strength)
            except Exception:
                log.exception("Screen capture failed for %s", screen.name())
        self.changed.emit()

    def paint(self, p, rect, screen):
        pm = self._frames.get(screen.name())
        if pm is None:
            p.fillRect(rect, QColor(brand.INK))
        else:
            p.drawPixmap(rect, pm, QRectF(pm.rect()))


class ImageBackdrop(Backdrop):
    def __init__(self, path: str, fit: str, fallback_color: str):
        super().__init__()
        self.fit = fit
        self.fallback = QColor(fallback_color)
        self.pixmap = QPixmap(path) if path else QPixmap()
        if self.pixmap.isNull():
            log.warning("Could not load image %r", path)

    @property
    def valid(self):
        return not self.pixmap.isNull()

    def paint(self, p, rect, screen):
        p.fillRect(rect, self.fallback)
        draw_fitted(p, rect, self.pixmap, self.fit)


class MediaBackdrop(Backdrop):
    """Animated GIF via QMovie, any other video via OpenCV (muted, looped)."""

    def __init__(self, path: str, fit: str, fallback_color: str):
        super().__init__()
        self.path = path
        self.fit = fit
        self.fallback = QColor(fallback_color)
        self.frame = QPixmap()
        self._movie: QMovie | None = None
        self._cap = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._next_video_frame)
        self.is_gif = Path(path).suffix.lower() in (".gif", ".webp", ".apng")
        self.valid = bool(path) and Path(path).is_file() and self._probe()

    def _probe(self) -> bool:
        if self.is_gif:
            return QMovie(self.path).isValid()
        cap = cv2.VideoCapture(self.path)
        ok = cap.isOpened() and cap.read()[0]
        cap.release()
        return bool(ok)

    def start(self, screens, live_capture_ok):
        if not self.valid:
            return
        if self.is_gif:
            self._movie = QMovie(self.path, parent=self)
            self._movie.setCacheMode(QMovie.CacheAll)
            self._movie.frameChanged.connect(self._on_movie_frame)
            self._movie.start()
        else:
            self._cap = cv2.VideoCapture(self.path)
            fps = self._cap.get(cv2.CAP_PROP_FPS) or 30
            fps = fps if 1 <= fps <= 120 else 30
            self._next_video_frame()
            self._timer.start(int(1000 / fps))

    def stop(self):
        self._timer.stop()
        if self._movie is not None:
            self._movie.stop()
            self._movie.deleteLater()
            self._movie = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def _on_movie_frame(self, _):
        self.frame = self._movie.currentPixmap()
        self.changed.emit()

    def _next_video_frame(self):
        if self._cap is None:
            return
        ok, frame = self._cap.read()
        if not ok:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._cap.read()
            if not ok:
                return
        h, w = frame.shape[:2]
        if w > MAX_VIDEO_WIDTH:
            frame = cv2.resize(frame, (MAX_VIDEO_WIDTH, int(h * MAX_VIDEO_WIDTH / w)), interpolation=cv2.INTER_AREA)
            h, w = frame.shape[:2]
        rgb = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        self.frame = QPixmap.fromImage(QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy())
        self.changed.emit()

    def paint(self, p, rect, screen):
        p.fillRect(rect, self.fallback)
        draw_fitted(p, rect, self.frame, self.fit)


def make_backdrop(s) -> Backdrop:
    if s.mode == "image":
        bd = ImageBackdrop(s.image_path, s.media_fit, s.color)
        if bd.valid:
            return bd
    elif s.mode == "media":
        bd = MediaBackdrop(s.media_path, s.media_fit, s.color)
        if bd.valid:
            return bd
        log.warning("Media %r unusable; falling back to blur", s.media_path)
    elif s.mode == "color":
        return ColorBackdrop(s.color)
    return BlurBackdrop(s.blur_strength, s.live_blur)


# --------------------------------------------------------------------------- windows
class OverlayWindow(QWidget):
    def __init__(self, manager: "OverlayManager", screen):
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput
            | Qt.WindowDoesNotAcceptFocus,
        )
        self.manager = manager
        self.screen_ref = screen
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setFocusPolicy(Qt.NoFocus)
        self.setWindowTitle(f"{APP_NAME} privacy overlay")
        self.setGeometry(screen.geometry())
        self.setWindowOpacity(0.0)
        self.capture_excluded = exclude_from_capture(int(self.winId()))
        self.anim = QPropertyAnimation(self, b"windowOpacity", self)
        self.anim.finished.connect(self._on_anim_done)

    def fade_to(self, target: float, ms: int) -> None:
        self.anim.stop()
        if target > 0 and not self.isVisible():
            self.setGeometry(self.screen_ref.geometry())
            self.show()
            self.raise_()
        if ms <= 0:
            self.setWindowOpacity(target)
            self._on_anim_done()
            return
        self.anim.setDuration(ms)
        self.anim.setStartValue(self.windowOpacity())
        self.anim.setEndValue(target)
        self.anim.start()

    def _on_anim_done(self):
        if self.windowOpacity() <= 0.001:
            self.hide()
            self.manager._window_hidden()

    def paintEvent(self, _):
        s = self.manager.settings
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        self.manager.backdrop.paint(p, rect, self.screen_ref)
        if s.dim > 0:
            p.fillRect(rect, QColor(0, 0, 0, int(255 * s.dim / 100)))
        if s.show_message and s.message.strip():
            self._paint_message(p, rect, s.message.strip())
        p.end()

    def _paint_message(self, p: QPainter, rect: QRectF, text: str) -> None:
        font = QFont("Segoe UI", 15)
        font.setWeight(QFont.DemiBold)
        p.setFont(font)
        fm = p.fontMetrics()
        text_w = min(fm.horizontalAdvance(text), int(rect.width() * 0.8))
        pad, icon = 22, 28
        w = text_w + icon + pad * 3
        h = max(fm.height(), icon) + pad * 1.4
        pill = QRectF(rect.center().x() - w / 2, rect.height() * 0.78 - h / 2, w, h)

        ink = QColor(brand.INK)
        ink.setAlpha(205)
        p.setPen(Qt.NoPen)
        p.setBrush(ink)
        p.drawRoundedRect(pill, h / 2, h / 2)

        ix, iy = pill.x() + pad, pill.center().y() - icon / 2
        p.drawPixmap(QRectF(ix, iy, icon, icon), brand.mark("amber"), QRectF(brand.mark("amber").rect()))

        p.setPen(QColor(brand.PAPER))
        text_rect = QRectF(ix + icon + pad * 0.8, pill.y(), text_w + 2, pill.height())
        p.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, fm.elidedText(text, Qt.ElideRight, text_w))


class OverlayManager(QObject):
    visibilityChanged = pyqtSignal(bool)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings.copy()
        self.backdrop: Backdrop = ColorBackdrop(self.settings.color)
        self.windows: list[OverlayWindow] = []
        self.shown = False
        self._watched_screens = set()
        app = QGuiApplication.instance()
        app.screenAdded.connect(self._rebuild)
        app.screenRemoved.connect(self._rebuild)
        self._rebuild()

    def _rebuild(self, *_):
        was_shown = self.shown
        for w in self.windows:
            w.anim.stop()
            w.hide()
            w.deleteLater()
        self.windows = [OverlayWindow(self, s) for s in QGuiApplication.screens()]
        for screen in QGuiApplication.screens():
            if id(screen) not in self._watched_screens:
                self._watched_screens.add(id(screen))
                screen.geometryChanged.connect(self._on_geometry)
        if was_shown:
            self.backdrop.stop()
            self._start_backdrop()
            for w in self.windows:
                w.fade_to(1.0, 0)

    def _on_geometry(self, *_):
        for w in self.windows:
            w.setGeometry(w.screen_ref.geometry())

    def apply_settings(self, settings) -> None:
        self.settings = settings.copy()
        if self.shown:
            self.backdrop.stop()
            self._start_backdrop()
        for w in self.windows:
            w.update()

    def _start_backdrop(self):
        try:
            self.backdrop.changed.disconnect(self._repaint)
        except TypeError:
            pass
        self.backdrop.stop()
        self.backdrop.deleteLater()
        self.backdrop = make_backdrop(self.settings)
        self.backdrop.changed.connect(self._repaint)
        live_ok = bool(self.windows) and all(w.capture_excluded for w in self.windows)
        self.backdrop.start(QGuiApplication.screens(), live_ok)

    def _repaint(self):
        for w in self.windows:
            if w.isVisible():
                w.update()

    def show(self) -> None:
        if self.shown:
            return
        self.shown = True
        # Capture/prepare the backdrop *before* the windows become visible.
        self._start_backdrop()
        for w in self.windows:
            w.fade_to(1.0, self.settings.fade_ms)
        self.visibilityChanged.emit(True)

    def hide(self) -> None:
        if not self.shown:
            return
        self.shown = False
        for w in self.windows:
            w.fade_to(0.0, self.settings.fade_ms)
        self.visibilityChanged.emit(False)

    def _window_hidden(self):
        if not self.shown and not any(w.isVisible() for w in self.windows):
            self.backdrop.stop()
