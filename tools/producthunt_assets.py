"""Build Product Hunt gallery images (1270x760) and the animated thumbnail.

Uses frames from the final demo video (dist/demo/final/umbra-demo.mp4) and the
documentation screenshots. Output: dist/producthunt/

    python tools/producthunt_assets.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
from PyQt5.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PyQt5.QtGui import (QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen,  # noqa: E402
                         QPixmap, QRadialGradient)
from PyQt5.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
from umbra import brand  # noqa: E402

OUT = ROOT / "dist" / "producthunt"
IMG = ROOT / "docs" / "assets" / "img"
DEMO = ROOT / "dist" / "demo" / "final" / "umbra-demo.mp4"
W, H = 1270, 760
S = 2  # render at 2x for crisp text, then downscale


def video_frame(t: float) -> QImage:
    cap = cv2.VideoCapture(str(DEMO))
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit(f"could not read {DEMO} at {t}s - record the demo first")
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()


def canvas():
    img = QImage(W * S, H * S, QImage.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.setRenderHint(QPainter.TextAntialiasing)
    p.scale(S, S)
    p.fillRect(QRectF(0, 0, W, H), QColor(brand.INK))
    glow = QRadialGradient(QPointF(W * 0.82, H * 0.08), W * 0.6)
    glow.setColorAt(0, QColor(255, 181, 71, 38))
    glow.setColorAt(1, QColor(255, 181, 71, 0))
    p.fillRect(QRectF(0, 0, W, H), glow)
    return img, p


def font(size, weight=QFont.Normal):
    f = QFont("Segoe UI", 1)
    f.setPixelSize(size)
    f.setWeight(weight)
    return f


def text(p, rect, s, size, color=brand.PAPER, weight=QFont.Normal, flags=Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap):
    p.setFont(font(size, weight))
    p.setPen(QColor(color))
    p.drawText(QRectF(*rect), flags, s)


def brand_row(p, x, y, size=26):
    mark = brand.mark("amber")
    p.drawPixmap(QRectF(x, y, size, size), mark, QRectF(mark.rect()))
    text(p, (x + size + 10, y - 4, 200, size + 10), "umbra", int(size * 1.05), weight=QFont.DemiBold)


def framed(p, img, rect, radius=14, border=True):
    r = QRectF(*rect)
    path = QPainterPath()
    path.addRoundedRect(r, radius, radius)
    p.save()
    p.setClipPath(path)
    scaled = img.scaled(int(r.width() * S), int(r.height() * S), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    sx = (scaled.width() - r.width() * S) / 2
    p.drawImage(r, scaled, QRectF(sx, 0, r.width() * S, r.height() * S))
    p.restore()
    if border:
        p.setPen(QPen(QColor(255, 255, 255, 60), 1.4))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)


def pill(p, x, y, label, accent=brand.AMBER):
    p.setFont(font(15, QFont.DemiBold))
    w = p.fontMetrics().horizontalAdvance(label) + 38
    r = QRectF(x, y, w, 32)
    p.setPen(QPen(QColor(accent), 1.2))
    p.setBrush(QColor(15, 15, 19, 220))
    p.drawRoundedRect(r, 16, 16)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(accent))
    p.drawEllipse(QPointF(x + 16, y + 16), 4.5, 4.5)
    p.setPen(QColor(brand.PAPER))
    p.drawText(r.adjusted(28, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, label)


def save(img, p, name):
    p.end()
    img.scaled(W, H, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).save(str(OUT / name))
    print("wrote", name)


# ---------------------------------------------------------------- slides
def slide_hero():
    img, p = canvas()
    brand_row(p, 64, 60)
    text(p, (64, 140, 480, 220), "Look away.\nYour screen\nhides itself.", 52, weight=QFont.DemiBold)
    text(p, (64, 356, 440, 200),
         "Umbra watches for your attention with your webcam and covers your screen "
         "the moment you look away. Look back and it's there again.", 21, color="#b9b5c2")
    pill(p, 64, 500, "Free & open source")
    pill(p, 64, 546, "Windows 10 & 11")
    pill(p, 64, 592, "Nothing leaves your PC")
    framed(p, video_frame(3.3), (540, 178, 680, 383))
    text(p, (540, 580, 680, 30), "Real recording: I looked away, so Umbra covered the screen.", 16,
         color="#8d899a", flags=Qt.AlignHCenter | Qt.AlignTop)
    save(img, p, "01-hero.png")


def slide_before_after():
    img, p = canvas()
    text(p, (0, 52, W, 60), "Your screen, only for your eyes", 38, weight=QFont.DemiBold, flags=Qt.AlignHCenter | Qt.AlignTop)
    text(p, (0, 104, W, 40), "A confidential inbox, and the same screen the moment you turn away.", 20,
         color="#b9b5c2", flags=Qt.AlignHCenter | Qt.AlignTop)
    framed(p, QImage(str(IMG / "demo-desktop.png")), (60, 180, 560, 315))
    framed(p, QImage(str(IMG / "mode-blur.png")), (650, 180, 560, 315))
    text(p, (60, 510, 560, 40), "Looking at the screen", 20, weight=QFont.DemiBold, flags=Qt.AlignHCenter | Qt.AlignTop)
    text(p, (650, 510, 560, 40), "Looked away: hidden in 0.7 s", 20, color=brand.AMBER, weight=QFont.DemiBold,
         flags=Qt.AlignHCenter | Qt.AlignTop)
    text(p, (0, 600, W, 60), "Back in 0.15 s when you look again  ·  Clicks pass through  ·  Covers every monitor", 18,
         color="#8d899a", flags=Qt.AlignHCenter | Qt.AlignTop)
    brand_row(p, W / 2 - 60, 680, 24)
    save(img, p, "02-before-after.png")


def slide_calibration():
    img, p = canvas()
    brand_row(p, 64, 60)
    text(p, (64, 150, 400, 150), "Calibrated to you in one minute", 40, weight=QFont.DemiBold)
    text(p, (64, 290, 380, 300),
         "A guided wizard has you look at the centre and edges of your screen, then away. "
         "Umbra sets its limits from your own head and eye movements, so it works wherever "
         "your camera sits.", 20, color="#b9b5c2")
    text(p, (64, 470, 380, 120), "10 steps  ·  about a minute  ·  redo any time", 17, color=brand.AMBER)
    framed(p, QImage(str(IMG / "wizard-edge.png")), (500, 180, 710, 400))
    save(img, p, "03-calibration.png")


def slide_modes():
    img, p = canvas()
    text(p, (0, 48, W, 60), "Hide it your way", 38, weight=QFont.DemiBold, flags=Qt.AlignHCenter | Qt.AlignTop)
    tiles = [("mode-blur.png", "Live blur"), ("mode-image.png", "Your own image"),
             ("mode-media.png", "GIF or video"), ("mode-color.png", "Solid colour")]
    tw, th, gap = 540, 243, 30
    x0 = (W - 2 * tw - gap) / 2
    for i, (f, label) in enumerate(tiles):
        x = x0 + (i % 2) * (tw + gap)
        y = 130 + (i // 2) * (th + 62)
        framed(p, QImage(str(IMG / f)), (x, y, tw, th))
        text(p, (x, y + th + 10, tw, 30), label, 19, weight=QFont.DemiBold, flags=Qt.AlignHCenter | Qt.AlignTop)
    save(img, p, "04-cover-styles.png")


def slide_private():
    img, p = canvas()
    brand_row(p, 64, 60)
    text(p, (64, 150, 560, 110), "Private by design", 44, weight=QFont.DemiBold)
    points = [
        ("On-device", "Every frame is processed in memory with Google MediaPipe. Nothing is recorded or uploaded."),
        ("Open source", "GPL-3.0. Read every line on GitHub."),
        ("Out of your way", "Lives in the tray. F8 toggles it; pause for up to an hour."),
        ("Never locks you out", "If the camera fails, your screen stays visible."),
    ]
    y = 250
    for title, body in points:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(brand.AMBER))
        p.drawRoundedRect(QRectF(64, y + 8, 22, 3), 1.5, 1.5)
        text(p, (100, y - 4, 540, 30), title, 21, weight=QFont.DemiBold)
        text(p, (100, y + 26, 540, 60), body, 18, color="#b9b5c2")
        y += 104
    framed(p, QImage(str(IMG / "tray-menu.png")), (760, 150, 420, 404), radius=12)
    save(img, p, "05-private.png")


# ---------------------------------------------------------------- thumbnail
def thumbnail():
    """240x240 animated GIF: an eclipse, the crescent's shadow sweeping across."""
    import imageio_ffmpeg
    import subprocess
    import tempfile

    N, size = 36, 240
    tmp = Path(tempfile.mkdtemp())
    for i in range(N):
        t = (i / N + 0.5) % 1  # start on the crescent: GIF thumbnails show only their first frame
        img = QImage(size * 2, size * 2, QImage.Format_RGB32)
        img.fill(QColor(brand.INK))
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(2, 2)
        import math
        # Full amber moon; the ink "shadow" slides down from above and settles into the
        # Umbra crescent (inner circle 0.75 r, offset 0.35 r up - from the mark's SVG path).
        c, r = QPointF(size / 2, size / 2 + 12), 80
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(brand.AMBER))
        p.drawEllipse(c, r, r)
        ease = (1 - math.cos(2 * math.pi * t)) / 2          # 0 -> 1 -> 0
        ease = min(1.0, ease * 1.35)                         # linger on the crescent
        start, end = -(r + 0.75 * r + 8), -0.35 * r          # fully above the moon -> crescent
        p.setBrush(QColor(brand.INK))
        p.drawEllipse(QPointF(c.x(), c.y() + start + (end - start) * ease), 0.75 * r, 0.75 * r)
        p.end()
        img.scaled(size, size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).save(str(tmp / f"f{i:03d}.png"))
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    vf = "split[a][b];[a]palettegen=max_colors=64[p];[b][p]paletteuse=dither=none"
    subprocess.run([ff, "-y", "-loglevel", "error", "-framerate", "18", "-i", str(tmp / "f%03d.png"),
                    "-vf", vf, "-loop", "0", str(OUT / "thumbnail.gif")], check=True)
    print("wrote thumbnail.gif")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    slide_hero()
    slide_before_after()
    slide_calibration()
    slide_modes()
    slide_private()
    thumbnail()


if __name__ == "__main__":
    main()
