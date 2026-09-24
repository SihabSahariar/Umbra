"""About window opened from the system tray."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QVBoxLayout

from . import APP_NAME, AUTHOR_EMAIL, AUTHOR_LINKEDIN, AUTHOR_NAME, __version__, brand
from .icons import app_icon


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.setWindowIcon(app_icon())
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumWidth(420)

        dark_ui = self.palette().window().color().lightness() < 128
        ratio = self.devicePixelRatioF()
        art = brand.logo(on_dark_background=dark_ui).scaledToHeight(int(64 * ratio), Qt.SmoothTransformation)
        art.setDevicePixelRatio(ratio)
        logo = QLabel()
        logo.setPixmap(art)
        logo.setAccessibleName(APP_NAME)

        title = QLabel(f"<span style='color:#7a828c'>Version {__version__}</span>")
        title.setAlignment(Qt.AlignRight | Qt.AlignBottom)

        description = QLabel(
            f"Privacy screen for your computer. {APP_NAME} uses your webcam to notice when you look "
            "away and hides your screen until you look back. Video is processed on your device "
            "and is never saved or sent anywhere."
        )
        description.setWordWrap(True)

        linkedin_label = AUTHOR_LINKEDIN.replace("https://www.", "").rstrip("/")
        author = QLabel(
            f"<b>Developed by {AUTHOR_NAME}</b><br>"
            f"Email: <a href='mailto:{AUTHOR_EMAIL}'>{AUTHOR_EMAIL}</a><br>"
            f"LinkedIn: <a href='{AUTHOR_LINKEDIN}'>{linkedin_label}</a>"
        )
        license_note = QLabel(
            f"<span style='color:#7a828c'>{APP_NAME} is free software, licensed under the "
            "<a href='https://www.gnu.org/licenses/gpl-3.0.html'>GNU GPL v3</a>. "
            "It comes with no warranty.</span>"
        )
        license_note.setWordWrap(True)
        license_note.setOpenExternalLinks(True)
        author.setTextFormat(Qt.RichText)
        author.setTextInteractionFlags(Qt.TextBrowserInteraction)
        author.setOpenExternalLinks(True)

        header = QHBoxLayout()
        header.addWidget(logo)
        header.addStretch(1)
        header.addWidget(title)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 16)
        layout.addLayout(header)
        layout.addSpacing(10)
        layout.addWidget(description)
        layout.addSpacing(10)
        layout.addWidget(author)
        layout.addSpacing(10)
        layout.addWidget(license_note)
        layout.addSpacing(6)
        layout.addWidget(buttons)
