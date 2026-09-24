"""Regenerate the documentation screenshots in docs/assets/img.

Every image is rendered by Umbra's own widgets and painting code. The cover
modes are drawn over a made-up demo desktop (never the real screen), and the
camera preview uses MediaPipe's public sample portrait, not a live webcam.

    python tools/screenshots.py
"""

import os
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "assets" / "img"
SAMPLE_FACE = "https://storage.googleapis.com/mediapipe-assets/business-person.png"

# Keep the real user's settings untouched.
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="umbra-shots-")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

from PyQt5.QtCore import QRectF, Qt  # noqa: E402
from PyQt5.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPixmap  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
app = QApplication([])

from umbra import brand, config, icons  # noqa: E402
from umbra.calibration import STEPS, Pose  # noqa: E402

W, H = 1600, 900


def save(pm: QPixmap, name: str, max_width: int = 1600) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if pm.width() > max_width:  # high-DPI grabs are 2x; keep web images light
        pm = pm.scaledToWidth(max_width, Qt.SmoothTransformation)
    pm.save(str(OUT / name))
    print("wrote", name, pm.width(), "x", pm.height())


class StubController:
    """Just enough of the controller for dialogs to render."""

    def __init__(self):
        self.settings = config.Settings(calibrated=True, first_run=False)
        self.tracker = None

    def __getattr__(self, name):  # suspend_hotkey, open_preview, ...
        return lambda *a, **k: None


# ------------------------------------------------------------------ demo desktop
def demo_desktop() -> QPixmap:
    """A fictional 'private' workspace: mail client with a sensitive message."""
    pm = QPixmap(W, H)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    p.fillRect(pm.rect(), QColor("#dfe6ee"))
    # window
    win = QRectF(60, 50, W - 120, H - 150)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#ffffff"))
    p.drawRoundedRect(win, 10, 10)
    p.setBrush(QColor("#f2f4f7"))
    p.drawRoundedRect(QRectF(win.x(), win.y(), win.width(), 44), 10, 10)
    p.fillRect(QRectF(win.x(), win.y() + 30, win.width(), 14), QColor("#f2f4f7"))
    for i, c in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        p.setBrush(QColor(c))
        p.drawEllipse(QRectF(win.x() + 18 + i * 22, win.y() + 16, 12, 12))
    p.setPen(QColor("#5b6572"))
    p.setFont(QFont("Segoe UI", 10))
    p.drawText(QRectF(win.x(), win.y(), win.width(), 44), Qt.AlignCenter, "Inbox — Mail")
    # sidebar list
    side = QRectF(win.x(), win.y() + 44, 380, win.height() - 44)
    p.fillRect(side, QColor("#f7f8fa"))
    mails = [
        ("Finance Team", "Q3 salary adjustments — confidential", True),
        ("Dr. Rivera's office", "Your test results are ready"),
        ("Bank Alerts", "Transfer of $12,480.00 completed"),
        ("Alex (Recruiter)", "Offer letter attached"),
        ("Legal", "Draft NDA — do not forward"),
        ("Sam", "Re: weekend plans"),
    ]
    for i, mail in enumerate(mails):
        who, subject = mail[0], mail[1]
        y = side.y() + 14 + i * 84
        if len(mail) > 2:
            p.fillRect(QRectF(side.x(), y - 6, side.width(), 80), QColor("#e6eefc"))
        p.setPen(QColor("#1d2530"))
        p.setFont(QFont("Segoe UI", 11, QFont.DemiBold))
        p.drawText(QRectF(side.x() + 22, y, 340, 26), Qt.AlignLeft | Qt.AlignVCenter, who)
        p.setPen(QColor("#5b6572"))
        p.setFont(QFont("Segoe UI", 10))
        p.drawText(QRectF(side.x() + 22, y + 28, 340, 24), Qt.AlignLeft | Qt.AlignVCenter, subject)
    # message body
    x0, y0 = side.right() + 50, win.y() + 90
    p.setPen(QColor("#1d2530"))
    p.setFont(QFont("Segoe UI", 20, QFont.DemiBold))
    p.drawText(int(x0), int(y0), "Q3 salary adjustments — confidential")
    p.setFont(QFont("Segoe UI", 11))
    p.setPen(QColor("#5b6572"))
    p.drawText(int(x0), int(y0 + 36), "From: Finance Team   To: Leadership   Today 09:42")
    p.setPen(QColor("#1d2530"))
    p.setFont(QFont("Segoe UI", 12))
    body = [
        "Hi all,",
        "",
        "Please find the proposed adjustments below. Do not share outside this group.",
        "",
    ]
    for i, line in enumerate(body):
        p.drawText(int(x0), int(y0 + 90 + i * 28), line)
    rows = [("Employee", "Current", "Proposed"), ("J. Carter", "$84,000", "$91,500"),
            ("M. Okafor", "$96,500", "$104,000"), ("L. Chen", "$72,300", "$79,000"),
            ("R. Novak", "$110,000", "$118,800")]
    ty = y0 + 90 + len(body) * 28
    for r, row in enumerate(rows):
        p.setFont(QFont("Segoe UI", 12, QFont.DemiBold if r == 0 else QFont.Normal))
        if r % 2 == 1:
            p.fillRect(QRectF(x0 - 10, ty + r * 40 - 26, 640, 40), QColor("#f4f6f9"))
        for c, cell in enumerate(row):
            p.drawText(int(x0 + c * 220), int(ty + r * 40), cell)
    p.setFont(QFont("Segoe UI", 12))
    p.drawText(int(x0), int(ty + len(rows) * 40 + 30), "Thanks, Finance")
    # taskbar
    p.fillRect(QRectF(0, H - 48, W, 48), QColor("#1f2329"))
    p.end()
    return pm


def render_overlay(settings, backdrop=None) -> QPixmap:
    from umbra.overlay import OverlayManager

    m = OverlayManager(settings)
    if backdrop is not None:
        m.backdrop = backdrop
    else:
        m._start_backdrop()
    win = m.windows[0]
    win.resize(W, H)
    pm = win.grab()
    m.backdrop.stop()
    return pm


def cover_modes(desktop: QPixmap, tmp: Path) -> None:
    from umbra.overlay import BlurBackdrop, blur_pixmap

    save(desktop, "demo-desktop.png")

    s = config.Settings(fade_ms=0)
    bd = BlurBackdrop(s.blur_strength, live=False)
    screen = QGuiApplication.primaryScreen()
    bd._frames[screen.name()] = blur_pixmap(desktop, s.blur_strength)
    save(render_overlay(s, bd), "mode-blur.png")

    # Custom image: the brand artwork stands in for a user's picture.
    art = tmp / "custom.png"
    brand.pixmap("logo", "png", "umbra-logo-amber-on-ink-4x.png").save(str(art))
    save(render_overlay(config.Settings(mode="image", image_path=str(art), media_fit="contain",
                                        dim=0, fade_ms=0)), "mode-image.png")

    # GIF/video: a single frame of a generated gradient clip.
    import cv2
    import numpy as np

    clip = tmp / "clip.avi"
    vw = cv2.VideoWriter(str(clip), cv2.VideoWriter_fourcc(*"MJPG"), 10, (640, 360))
    yy, xx = np.mgrid[0:360, 0:640]
    frame = np.zeros((360, 640, 3), np.uint8)
    frame[..., 0] = (60 + 80 * xx / 640).astype(np.uint8)
    frame[..., 1] = (40 + 60 * yy / 360).astype(np.uint8)
    frame[..., 2] = (120 + 100 * (1 - xx / 640)).astype(np.uint8)
    mark = cv2.imread(brand.asset("logo", "png", "umbra-mark-amber.png"), cv2.IMREAD_UNCHANGED)
    mark = cv2.resize(mark, (200, 200), interpolation=cv2.INTER_AREA)
    alpha = mark[..., 3:4].astype(float) / 255
    y0, x0 = 80, 220
    roi = frame[y0:y0 + 200, x0:x0 + 200].astype(float)
    frame[y0:y0 + 200, x0:x0 + 200] = (roi * (1 - alpha) + mark[..., :3] * alpha).astype(np.uint8)
    for _ in range(3):
        vw.write(frame)
    vw.release()
    save(render_overlay(config.Settings(mode="media", media_path=str(clip), dim=10, fade_ms=0)), "mode-media.png")

    save(render_overlay(config.Settings(mode="color", fade_ms=0)), "mode-color.png")


# ------------------------------------------------------------------ app windows
def tray_menu() -> None:
    from umbra.app import Controller

    c = Controller(app)
    c._refresh_ui()
    c.menu.adjustSize()
    save(c.menu.grab(), "tray-menu.png")
    c.hotkey.unregister()


def tray_states() -> None:
    from unittest import mock

    pm = QPixmap(4 * 150, 2 * 110)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    labels = {"focused": "Protecting", "away": "Screen hidden", "disabled": "Paused", "error": "Camera problem"}
    for row, (light, bg, fg) in enumerate(((False, "#202020", "#c8c8c8"), (True, "#f3f3f3", "#404040"))):
        p.fillRect(QRectF(0, row * 110, pm.width(), 110), QColor(bg))
        with mock.patch.object(brand, "taskbar_is_light", return_value=light):
            icons._tray_icon.cache_clear()
            for col, state in enumerate(labels):
                p.drawPixmap(59 + col * 150, row * 110 + 22, icons.state_icon(state).pixmap(32, 32))
                p.setPen(QColor(fg))
                p.setFont(QFont("Segoe UI", 10))
                p.drawText(QRectF(col * 150, row * 110 + 64, 150, 30), Qt.AlignCenter, labels[state])
    p.end()
    save(pm, "tray-states.png")


def dialogs() -> None:
    from umbra.about_dialog import AboutDialog
    from umbra.settings_dialog import SettingsDialog

    ctl = StubController()
    d = SettingsDialog(ctl)
    tabs = d.findChild(__import__("PyQt5.QtWidgets", fromlist=["QTabWidget"]).QTabWidget)
    for i, name in enumerate(("settings-general", "settings-detection", "settings-appearance")):
        tabs.setCurrentIndex(i)
        d.adjustSize()
        save(d.grab(), f"{name}.png")

    a = AboutDialog()
    a.adjustSize()
    save(a.grab(), "about.png")


def wizard() -> None:
    from umbra.calibration_wizard import CalibrationWizard

    wz = CalibrationWizard(StubController())
    wz.resize(1280, 720)  # a smaller "screen" keeps the panel legible in thumbnails
    face = QImage(str(sample_face()))
    face = face.copy(0, 0, face.width(), face.width() * 3 // 4)  # 4:3 webcam framing
    wz.video.show()
    wz._have_frames = True
    wz.video.setPixmap(QPixmap.fromImage(face).scaled(wz.video.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
    for idx, name in ((0, "wizard-centre"), (1, "wizard-edge"), (5, "wizard-away")):
        wz._show_step(idx)
        save(wz.grab(), f"{name}.png")
    wz.poses = {s.key: Pose(0, 10, 0.05) for s in STEPS}
    wz.poses.update(screen_left=Pose(-12, 10, .2), screen_right=Pose(12, 10, .2), screen_top=Pose(0, 2, .05),
                    screen_bottom=Pose(0, 22, .05), away_left=Pose(-50, 10, .1), away_right=Pose(50, 10, .1),
                    away_up=Pose(0, -20, .05), away_down=Pose(0, 50, .05), eyes_away=Pose(0, 10, .8))
    wz._show_summary()
    save(wz.grab(), "wizard-summary.png")


def sample_face() -> Path:
    path = Path(tempfile.gettempdir()) / "umbra-sample-face.png"
    if not path.exists():
        urllib.request.urlretrieve(SAMPLE_FACE, path)
    return path


def camera_preview() -> None:
    """Run the real tracker pipeline on the sample portrait and show it in the preview dialog."""
    import cv2
    import numpy as np

    from umbra.tracker import FaceTracker, ensure_model, thresholds_from_settings  # before mediapipe
    from mediapipe import Image, ImageFormat
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions, RunningMode

    from umbra.gaze import decide
    from umbra.preview import PreviewDialog

    img = cv2.imread(str(sample_face()))
    img = cv2.resize(img, (640, int(640 * img.shape[0] / img.shape[1])))
    img = np.ascontiguousarray(img[: 480])  # webcam-like 4:3 framing (head and shoulders)
    opts = FaceLandmarkerOptions(base_options=BaseOptions(model_asset_buffer=ensure_model()),
                                 running_mode=RunningMode.IMAGE, num_faces=2,
                                 output_face_blendshapes=True, output_facial_transformation_matrixes=True)
    ctl = StubController()
    with FaceLandmarker.create_from_options(opts) as lm:
        rgb = np.ascontiguousarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        result = lm.detect(Image(image_format=ImageFormat.SRGB, data=rgb))
    obs = FaceTracker._observations(result)
    ctl.settings.pitch_offset = obs[0].pitch if obs else 0.0  # as if calibrated for this sitter
    decision = decide(obs, thresholds_from_settings(ctl.settings))
    frame = FaceTracker._render_preview(img, result, decision, decision.looking)

    d = PreviewDialog(ctl)
    d.resize(720, 660)
    d.video.setPixmap(QPixmap.fromImage(frame).scaled(680, 510, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    save(d.grab(), "camera-preview.png")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cover_modes(demo_desktop(), Path(tmp))
    tray_menu()
    tray_states()
    dialogs()
    wizard()
    camera_preview()


if __name__ == "__main__":
    main()
