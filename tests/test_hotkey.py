import pytest
from PyQt5.QtWidgets import QApplication

from umbra.hotkey import MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, HotkeyError, parse_hotkey


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.mark.parametrize(
    "text, expected",
    [
        ("F8", (0, 0x77)),
        ("F11", (0, 0x7A)),
        ("F1", (0, 0x70)),
        ("Ctrl+Alt+B", (MOD_CONTROL | MOD_ALT, ord("B"))),
        ("Shift+Meta+9", (MOD_SHIFT | MOD_WIN, ord("9"))),
        ("Ctrl+Space", (MOD_CONTROL, 0x20)),
        ("Pause", (0, 0x13)),
    ],
)
def test_parse(text, expected):
    assert parse_hotkey(text) == expected


@pytest.mark.parametrize("text", ["", "Ctrl+A, Ctrl+B", "Ctrl"])
def test_rejects_invalid(text):
    with pytest.raises(HotkeyError):
        parse_hotkey(text)
