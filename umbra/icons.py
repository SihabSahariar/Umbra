"""App and tray icons built from the Umbra brand assets."""

from functools import lru_cache

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from . import brand

ERROR_RED = "#E5484D"


@lru_cache(maxsize=1)
def app_icon() -> QIcon:
    icon = QIcon(brand.asset(*brand.APP_ICO))
    for parts in brand.APP_PNGS:
        pm = brand.pixmap(*parts)
        if not pm.isNull():
            icon.addPixmap(pm)
    return icon


def _derive(base: QIcon, opacity: float = 1.0, badge: str | None = None) -> QIcon:
    """Re-draw every size of `base`, optionally faded and/or with a status dot."""
    out = QIcon()
    for size in base.availableSizes() or []:
        src = base.pixmap(size)
        pm = QPixmap(src.size())
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(opacity)
        p.drawPixmap(0, 0, src)
        if badge:
            p.setOpacity(1.0)
            s = pm.width()
            r = s * 0.2
            centre = QPointF(s - r - s * 0.02, s - r - s * 0.02)
            p.setPen(QPen(QColor(brand.INK), max(1.0, s * 0.06)))
            p.setBrush(QColor(badge))
            p.drawEllipse(centre, r, r)
        p.end()
        out.addPixmap(pm)
    return out


@lru_cache(maxsize=None)
def _tray_icon(state: str, light_taskbar: bool) -> QIcon:
    base = QIcon(brand.asset(*brand.TRAY_ICO["dark" if light_taskbar else "light"]))
    if state == "away":
        return QIcon(brand.asset(*brand.TRAY_ICO["amber"]))  # screen is being hidden
    if state == "disabled":
        return _derive(base, opacity=0.38)
    if state == "error":
        return _derive(base, badge=ERROR_RED)
    return base


def state_icon(state: str) -> QIcon:
    """Tray icon for focused | away | disabled | error, matched to the taskbar theme."""
    return _tray_icon(state, brand.taskbar_is_light())
