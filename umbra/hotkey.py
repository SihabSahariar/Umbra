"""System-wide hotkey using Win32 RegisterHotKey (no extra dependencies)."""

import ctypes
import ctypes.wintypes
import logging

from PyQt5.QtCore import QAbstractNativeEventFilter, QObject, Qt, pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QApplication

from .winutil import IS_WINDOWS

log = logging.getLogger(__name__)

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
HOTKEY_ID = 0xB10E

_SPECIAL_VK = {
    Qt.Key_Space: 0x20, Qt.Key_Escape: 0x1B, Qt.Key_Tab: 0x09, Qt.Key_Backspace: 0x08,
    Qt.Key_Return: 0x0D, Qt.Key_Enter: 0x0D, Qt.Key_Insert: 0x2D, Qt.Key_Delete: 0x2E,
    Qt.Key_Home: 0x24, Qt.Key_End: 0x23, Qt.Key_PageUp: 0x21, Qt.Key_PageDown: 0x22,
    Qt.Key_Left: 0x25, Qt.Key_Up: 0x26, Qt.Key_Right: 0x27, Qt.Key_Down: 0x28,
    Qt.Key_Pause: 0x13, Qt.Key_Print: 0x2C, Qt.Key_ScrollLock: 0x91,
    Qt.Key_Minus: 0xBD, Qt.Key_Equal: 0xBB, Qt.Key_Plus: 0xBB, Qt.Key_Comma: 0xBC,
    Qt.Key_Period: 0xBE, Qt.Key_Slash: 0xBF, Qt.Key_Semicolon: 0xBA,
    Qt.Key_Apostrophe: 0xDE, Qt.Key_BracketLeft: 0xDB, Qt.Key_BracketRight: 0xDD,
    Qt.Key_Backslash: 0xDC, Qt.Key_QuoteLeft: 0xC0,
}


class HotkeyError(ValueError):
    pass


def parse_hotkey(text: str) -> tuple[int, int]:
    """Convert e.g. 'Ctrl+Alt+B' or 'F11' into Win32 (modifiers, virtual key)."""
    seq = QKeySequence.fromString(text.strip(), QKeySequence.PortableText)
    if seq.count() != 1:
        raise HotkeyError(f"'{text}' is not a single key combination")
    combo = int(seq[0])
    key = combo & ~int(Qt.KeyboardModifierMask)
    qmods = combo & int(Qt.KeyboardModifierMask)

    mods = 0
    if qmods & int(Qt.ControlModifier):
        mods |= MOD_CONTROL
    if qmods & int(Qt.AltModifier):
        mods |= MOD_ALT
    if qmods & int(Qt.ShiftModifier):
        mods |= MOD_SHIFT
    if qmods & int(Qt.MetaModifier):
        mods |= MOD_WIN

    if Qt.Key_A <= key <= Qt.Key_Z or Qt.Key_0 <= key <= Qt.Key_9:
        vk = key  # Qt and Win32 share ASCII codes here
    elif Qt.Key_F1 <= key <= Qt.Key_F24:
        vk = 0x70 + (key - Qt.Key_F1)
    elif key in _SPECIAL_VK:
        vk = _SPECIAL_VK[key]
    else:
        raise HotkeyError(f"Unsupported key in '{text}'")
    return mods, vk


class _MsgFilter(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self._callback = callback

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self._callback()
                return True, 0
        return False, 0


class GlobalHotkey(QObject):
    activated = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._registered = False
        self.current = ""
        self._filter = _MsgFilter(self.activated.emit)
        if IS_WINDOWS:
            QApplication.instance().installNativeEventFilter(self._filter)

    def register(self, text: str) -> None:
        """Register `text` as the hotkey. Raises HotkeyError on failure."""
        self.unregister()
        if not text:
            return
        mods, vk = parse_hotkey(text)
        if not IS_WINDOWS:
            raise HotkeyError("Global hotkeys are only supported on Windows")
        if not ctypes.windll.user32.RegisterHotKey(None, HOTKEY_ID, mods | MOD_NOREPEAT, vk):
            raise HotkeyError(f"'{text}' is already in use by another application")
        self._registered = True
        self.current = text
        log.info("Registered hotkey %s", text)

    def unregister(self) -> None:
        if self._registered and IS_WINDOWS:
            ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
        self._registered = False
        self.current = ""
