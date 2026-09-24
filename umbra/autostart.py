"""Launch-at-login via the per-user Run registry key (no admin rights needed)."""

import logging
import sys
from pathlib import Path

from . import APP_NAME
from .paths import LEGACY_NAMES
from .winutil import IS_WINDOWS

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --background'
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    interpreter = pythonw if pythonw.exists() else exe
    main = Path(__file__).resolve().parent.parent / "main.py"
    return f'"{interpreter}" "{main}" --background'


def is_enabled() -> bool:
    if not IS_WINDOWS:
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    if not IS_WINDOWS:
        return
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        for legacy in LEGACY_NAMES:  # never launch the old build alongside this one
            try:
                winreg.DeleteValue(key, legacy)
            except FileNotFoundError:
                pass
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, launch_command())
            log.info("Autostart enabled")
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
                log.info("Autostart disabled")
            except FileNotFoundError:
                pass
