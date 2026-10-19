"""Open only the current music dialog; no translator capture or settings writes."""
from pathlib import Path
import argparse
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication
from ui import config, i18n, theme
from ui.music_dialog import MusicDialog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--missing-driver", action="store_true",
                        help="Show missing-setup layout; Install checks this PC and runs real setup if needed")
    args = parser.parse_args()
    settings = config.load()
    i18n.set_lang(settings.ui_lang)
    app = QApplication([])
    app.setStyleSheet(theme.style_sheet())
    if args.missing_driver:
        with patch("ui.music_dialog.attachment_for", return_value=None):
            dialog = MusicDialog(settings)
        dialog.setWindowTitle("Music to microphone — missing driver preview")
        # Keep this development-only simulation isolated from actual setup checks.
        dialog.refresh_button.setEnabled(False)
        dialog._poll_timer.stop()
    else:
        dialog = MusicDialog(settings)
    dialog.show()
    if args.missing_driver:
        dialog.offer_setup()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
