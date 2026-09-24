# Changelog

## 1.0.2

**Fixed**
- Corrected the contact email in the About window (sihabsahariarcse@gmail.com).
- Links now point to the new site address, https://sihabsahariar.com/Umbra/ (the old github.io address still redirects).

## 1.0.1

**Fixed**
- On high-DPI displays (125–200% scaling), the cover message was cut off ("Look at your screen to contin…"). The full message is now shown.

**Added**
- `tools/record_demo.py` records a demo video: your screen with the webcam in the corner and spoken cues.
- Setting `UMBRA_CAPTURABLE=1` makes the cover visible to screen recorders (it's normally hidden from them so live blur works).

## 1.0.0

First release: webcam attention detection with MediaPipe, a guided 10-step calibration, blur / image / GIF-video / solid-colour covers, a system-tray app with an F8 hotkey, start with Windows, and an Inno Setup installer.
