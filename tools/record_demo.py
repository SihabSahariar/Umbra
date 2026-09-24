"""Record a demo of Umbra: the real screen, with the webcam picture-in-picture.

Runs Umbra itself (the webcam can only be opened once), makes its cover visible
to screen capture, and follows a spoken script so the person on camera knows
when to look away and back:

    0 s   "Look at the screen"
    6 s   "Turn your head away"
    11 s  "Look back"
    16 s  "Look down at your phone"
    21 s  "Look back"
    27 s  "Done"

    python tools/record_demo.py [--out dist/demo] [--width 1280] [--gif-width 960]

Writes umbra-demo.mp4 (H.264) and umbra-demo.gif to --out.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CUES = [(0, 1200, "Look at the screen"), (6, 900, "Turn your head away"), (11, 900, "Look back"),
        (16, 900, "Look down at your phone"), (21, 900, "Look back")]
DURATION = 27
FPS = 12
MODE = os.environ.get("UMBRA_DEMO_MODE", "")  # e.g. "blur" to override the saved cover style


class Voice:
    """Speaks cues with the built-in Windows voice (one persistent process, low latency)."""

    SCRIPT = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              "$s.Rate = 1; while (($l = [Console]::In.ReadLine()) -ne $null) { $s.Speak($l) }")

    def __init__(self):
        try:
            self.proc = subprocess.Popen(["powershell", "-NoProfile", "-Command", self.SCRIPT],
                                         stdin=subprocess.PIPE, text=True, creationflags=0x08000000)
        except OSError:
            self.proc = None

    def say(self, text: str) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.stdin.write(text + "\n")
            self.proc.stdin.flush()

    def close(self) -> None:
        if self.proc:
            try:
                self.proc.stdin.close()
            except OSError:
                pass


def prepare_settings() -> None:
    """Use a temporary copy of the user's settings (keeps their calibration, never writes back)."""
    real = Path(os.environ.get("APPDATA", "")) / "Umbra" / "settings.json"
    data = json.loads(real.read_text(encoding="utf-8")) if real.is_file() else {}
    data.update(enabled=True, notifications=False, first_run=False, calibrated=True, autostart=False)
    if MODE:
        data["mode"] = MODE
    tmp = Path(tempfile.mkdtemp(prefix="umbra-demo-"))
    (tmp / "Umbra").mkdir()
    (tmp / "Umbra" / "settings.json").write_text(json.dumps(data), encoding="utf-8")
    os.environ["APPDATA"] = str(tmp)
    os.environ["UMBRA_CAPTURABLE"] = "1"
    print("calibrated settings found" if real.is_file() else "no saved settings - using defaults")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "dist" / "demo"))
    ap.add_argument("--width", type=int, default=1280, help="video width")
    ap.add_argument("--gif-width", type=int, default=960)
    ap.add_argument("--countdown", type=int, default=5)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    prepare_settings()

    import cv2
    import numpy as np
    from PyQt5.QtCore import QPointF, QRectF, Qt, QTimer
    from PyQt5.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPainterPath, QPen
    from PyQt5.QtWidgets import QApplication

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)

    from umbra import brand
    from umbra.app import Controller

    ctl = Controller(app)
    ctl.start(background=True)
    tracker = ctl.tracker
    tracker.clean_preview = True
    tracker.set_preview(True)

    state = {"cam": None, "writer": None, "t0": None, "written": 0, "cue": 0}
    tracker.previewFrame.connect(lambda img: state.__setitem__("cam", img))

    screen = QGuiApplication.primaryScreen()
    raw_path = out / "umbra-demo-raw.avi"

    def compose() -> QImage:
        shot = screen.grabWindow(0).toImage()
        frame = shot.scaledToWidth(args.width, Qt.SmoothTransformation).convertToFormat(QImage.Format_RGB888)
        frame.setDevicePixelRatio(1.0)  # high-DPI grabs carry dpr 2; draw in real pixels
        W, H = frame.width(), frame.height()
        p = QPainter(frame)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        away = not ctl.focused
        accent = QColor(brand.AMBER) if away else QColor(brand.PAPER)

        # Webcam picture-in-picture, bottom right.
        cam = state["cam"]
        pw = int(W * 0.24)
        ph = int(pw * 3 / 4)
        box = QRectF(W - pw - 22, H - ph - 22, pw, ph)
        path = QPainterPath()
        path.addRoundedRect(box, 14, 14)
        p.save()
        p.setClipPath(path)
        p.fillRect(box, QColor(brand.INK))
        if cam is not None and not cam.isNull():
            scaled = cam.scaled(pw, ph, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            p.drawImage(box, scaled, QRectF((scaled.width() - pw) / 2, (scaled.height() - ph) / 2, pw, ph))
        p.restore()
        p.setPen(QPen(accent, 3))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        # State badge on the webcam view.
        label = "Looked away - screen hidden" if away else "Looking at the screen"
        f = QFont("Segoe UI", max(9, int(W / 110)))
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        fm = p.fontMetrics()
        bw, bh = fm.horizontalAdvance(label) + 34, fm.height() + 12
        badge = QRectF(box.x() + 10, box.y() + 10, bw, bh)
        ink = QColor(brand.INK)
        ink.setAlpha(210)
        p.setPen(Qt.NoPen)
        p.setBrush(ink)
        p.drawRoundedRect(badge, bh / 2, bh / 2)
        p.setBrush(accent)
        p.drawEllipse(QPointF(badge.x() + 14, badge.center().y()), 4.5, 4.5)
        p.setPen(QColor(brand.PAPER))
        p.drawText(badge.adjusted(24, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, label)

        # Small brand mark, bottom left.
        mark = brand.mark("amber")
        ms = int(W / 42)
        p.drawPixmap(QRectF(22, H - ms - 26, ms, ms), mark, QRectF(mark.rect()))
        f2 = QFont("Segoe UI", max(10, int(W / 80)))
        f2.setWeight(QFont.DemiBold)
        p.setFont(f2)
        p.setPen(QColor(0, 0, 0, 140))
        p.drawText(QPointF(22 + ms + 9, H - 26 - ms * 0.22 + 1), "umbra")
        p.setPen(QColor(brand.PAPER))
        p.drawText(QPointF(22 + ms + 8, H - 26 - ms * 0.22), "umbra")
        p.end()
        return frame

    def to_bgr(img: QImage) -> np.ndarray:
        ptr = img.constBits()
        ptr.setsize(img.byteCount())
        arr = np.frombuffer(ptr, np.uint8).reshape(img.height(), img.bytesPerLine())[:, : img.width() * 3]
        return cv2.cvtColor(arr.reshape(img.height(), img.width(), 3), cv2.COLOR_RGB2BGR)

    def tick():
        if state["t0"] is None:
            return
        elapsed = time.monotonic() - state["t0"]
        # Cue beeps.
        while state["cue"] < len(CUES) and elapsed >= CUES[state["cue"]][0]:
            at, freq, what = CUES[state["cue"]]
            voice.say(what)
            print(f"  {at:>2}s  {what}", flush=True)
            state["cue"] += 1
        frame = to_bgr(compose())
        if state["writer"] is None:
            h, w = frame.shape[:2]
            state["writer"] = cv2.VideoWriter(str(raw_path), cv2.VideoWriter_fourcc(*"MJPG"), FPS, (w, h))
        # Keep real-time pacing: repeat the frame if a grab ran late.
        target = int(elapsed * FPS) + 1
        while state["written"] < target:
            state["writer"].write(frame)
            state["written"] += 1
        if elapsed >= DURATION:
            finish()

    def finish():
        timer.stop()
        state["t0"] = None
        state["writer"].release()
        voice.say("Done. Thank you.")
        print("recording finished", flush=True)
        ctl.quit()

    voice = Voice()
    timer = QTimer(interval=int(1000 / FPS), timeout=tick)
    countdown = {"n": args.countdown}

    def count():
        if countdown["n"] > 0:
            print(f"starting in {countdown['n']}...", flush=True)
            voice.say(str(countdown["n"]))
            countdown["n"] -= 1
            QTimer.singleShot(1000, count)
        else:
            state["t0"] = time.monotonic()
            timer.start()

    # Give the camera a moment to start before counting down.
    QTimer.singleShot(3000, count)
    app.exec_()
    time.sleep(1.5)  # let "Done" finish speaking
    voice.close()

    # ---- encode: H.264 MP4 for social posts, palette-optimised GIF
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    mp4 = out / "umbra-demo.mp4"
    gif = out / "umbra-demo.gif"
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(raw_path), "-c:v", "libx264", "-preset", "slow",
                    "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)], check=True)
    vf = (f"fps=10,scale={args.gif_width}:-1:flags=lanczos,split[a][b];"
          "[a]palettegen=max_colors=160:stats_mode=diff[p];"
          "[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle")
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(raw_path), "-vf", vf, "-loop", "0", str(gif)],
                   check=True)
    raw_path.unlink(missing_ok=True)
    shutil.rmtree(Path(os.environ["APPDATA"]), ignore_errors=True)
    for f in (mp4, gif):
        print(f"wrote {f}  ({f.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
