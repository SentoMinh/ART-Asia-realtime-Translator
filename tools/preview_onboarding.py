"""Open the first-run language screen or the guided manual without changing saved settings.

    python tools/preview_onboarding.py [--lang en|zh|vi] [--language-screen]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ui import theme  # noqa: E402
from ui.config import Settings  # noqa: E402
from ui.demo_backend import DemoBackend  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lang", choices=["en", "zh", "vi"], default="en")
    parser.add_argument("--language-screen", action="store_true",
                        help="Show the first-run language picker instead of the manual")
    parser.add_argument("--fresh", action="store_true",
                        help="Simulate a brand-new profile: language, setup, then the manual")
    args = parser.parse_args()

    app = QApplication(sys.argv[:1])
    app.setStyleSheet(theme.style_sheet())
    if args.fresh:
        settings = Settings(ui_lang=args.lang)
    else:
        settings = Settings(
            ui_lang=args.lang,
            ui_lang_chosen=True,
            first_run_done=True,
            tour_done=False,
        )
    window = MainWindow(DemoBackend(), settings, save=lambda _settings: None)
    window.show()
    if args.fresh:
        QTimer.singleShot(100, window.begin_onboarding)
    elif args.language_screen:
        window.settings.ui_lang_chosen = False
        QTimer.singleShot(100, window.show_language_prompt)
    else:
        QTimer.singleShot(100, window.show_tour)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
