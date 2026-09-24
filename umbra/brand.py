"""Umbra brand: colours, asset locations and theme detection.

All artwork comes from assets/umbra-brand (see its README.txt).
"""

import logging
from functools import lru_cache

from PyQt5.QtGui import QPixmap

from . import paths
from .winutil import IS_WINDOWS

log = logging.getLogger(__name__)

AMBER = "#FFB547"
INK = "#0F0F13"
INK_2 = "#2A2833"
PAPER = "#F6F4EF"


def asset(*parts: str) -> str:
    return str(paths.resource_root().joinpath("assets", "umbra-brand", *parts))


APP_ICO = ("icons", "umbra.ico")
APP_PNGS = tuple(("icons", "png", f"umbra-{s}.png") for s in (16, 24, 32, 48, 64, 128, 256, 512, 1024))
TRAY_ICO = {
    "light": ("icons", "tray-light.ico"),  # light mark, for a dark taskbar
    "dark": ("icons", "tray-dark.ico"),    # dark mark, for a light taskbar
    "amber": ("icons", "tray-amber.ico"),
}


@lru_cache(maxsize=None)
def pixmap(*parts: str) -> QPixmap:
    pm = QPixmap(asset(*parts))
    if pm.isNull():
        log.warning("Missing brand asset: %s", "/".join(parts))
    return pm


def mark(variant: str = "amber") -> QPixmap:
    """The crescent mark (1024 px). variant: amber | light | dark."""
    return pixmap("logo", "png", f"umbra-mark-{variant}.png")


def logo(on_dark_background: bool) -> QPixmap:
    """Horizontal logo (mark + wordmark) rendered for the given background."""
    name = "umbra-logo-light-4x.png" if on_dark_background else "umbra-logo-dark-4x.png"
    return pixmap("logo", "png", name)


def taskbar_is_light() -> bool:
    """True when Windows uses a light taskbar (so the tray needs the dark mark)."""
    if not IS_WINDOWS:
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            value, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
            return bool(value)
    except OSError:
        return False  # Windows default is a dark taskbar
