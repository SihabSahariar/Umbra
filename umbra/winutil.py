"""Small Win32 helpers (no-ops on other platforms)."""

import ctypes
import logging
import os

log = logging.getLogger(__name__)

IS_WINDOWS = os.name == "nt"
WDA_NONE = 0x0
WDA_EXCLUDEFROMCAPTURE = 0x11  # Windows 10 2004+


def exclude_from_capture(hwnd: int) -> bool:
    """Hide a window from screen capture so we can grab a live screen behind it."""
    if not IS_WINDOWS:
        return False
    try:
        user32 = ctypes.windll.user32
        if not user32.SetWindowDisplayAffinity(ctypes.c_void_p(hwnd), WDA_EXCLUDEFROMCAPTURE):
            return False
        value = ctypes.c_uint(0)
        user32.GetWindowDisplayAffinity(ctypes.c_void_p(hwnd), ctypes.byref(value))
        return value.value == WDA_EXCLUDEFROMCAPTURE
    except Exception:
        log.debug("SetWindowDisplayAffinity failed", exc_info=True)
        return False


def set_app_user_model_id(app_id: str) -> None:
    """Gives the process its own taskbar/notification identity."""
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        log.debug("SetCurrentProcessExplicitAppUserModelID failed", exc_info=True)
