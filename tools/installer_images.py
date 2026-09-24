"""Generate the Inno Setup wizard images in installer/ from the brand kit.

    python tools/installer_images.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt5.QtCore import QRectF, Qt  # noqa: E402
from PyQt5.QtGui import QColor, QImage, QLinearGradient, QPainter, QPixmap  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
from umbra import brand  # noqa: E402

OUT = ROOT / "installer"


def large(scale: int) -> QImage:
    """Left-hand banner on the Welcome/Finished pages (164x314 at 100%)."""
    w, h = 164 * scale, 314 * scale
    img = QImage(w, h, QImage.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    grad = QLinearGradient(0, 0, 0, h)
    grad.setColorAt(0, QColor(brand.INK_2))
    grad.setColorAt(1, QColor(brand.INK))
    p.fillRect(img.rect(), grad)
    mark = brand.mark("amber")
    size = 96 * scale
    p.drawPixmap(QRectF((w - size) / 2, h * 0.30 - size / 2, size, size), mark, QRectF(mark.rect()))
    logo = brand.logo(on_dark_background=True)
    # Crop the wordmark (right part of the horizontal logo) and centre it below the mark.
    word = logo.copy(int(logo.width() * 0.33), 0, int(logo.width() * 0.67), logo.height())
    word_w = 104 * scale
    word_h = word_w * word.height() / word.width()
    p.drawPixmap(QRectF((w - word_w) / 2, h * 0.30 + size * 0.62, word_w, word_h), word, QRectF(word.rect()))
    p.end()
    return img


def small(scale: int) -> QImage:
    """Top-right image on the inner pages (55x58 at 100%)."""
    w, h = 55 * scale, 58 * scale
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    icon = brand.pixmap("icons", "png", "umbra-256.png")
    side = min(w, h) - 4 * scale
    p.drawPixmap(QRectF((w - side) / 2, (h - side) / 2, side, side), icon, QRectF(icon.rect()))
    p.end()
    return img


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for scale in (1, 2):
        for name, img in ((f"wizard-large-{scale}x.bmp", large(scale)), (f"wizard-small-{scale}x.bmp", small(scale))):
            img.save(str(OUT / name), "BMP")
            print("wrote", name, img.width(), "x", img.height())


if __name__ == "__main__":
    main()
