"""Draw the window and the settings to PNG files, to check the look without opening them.

    python tools/snapshot_ui.py [out_dir] [--backdrop N] [--font N] [--lang en|zh|vi] [--hide-bars]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ui import theme  # noqa: E402
from ui.backend import Status, Utterance  # noqa: E402
from ui.config import Settings  # noqa: E402
from ui.demo_backend import SCRIPT, DemoBackend  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.settings_window import SettingsWindow  # noqa: E402
from vr.main import attach_wrist  # noqa: E402


def over_game(widget) -> QImage:
    """The widget drawn over a bright fake game picture, to judge readability."""
    shot = widget.grab().toImage()
    image = QImage(shot.size(), QImage.Format_ARGB32)
    painter = QPainter(image)
    sky = QLinearGradient(0, 0, image.width(), image.height())
    sky.setColorAt(0, QColor("#ffcf7a"))
    sky.setColorAt(0.5, QColor("#e86a6a"))
    sky.setColorAt(1, QColor("#3a7bd5"))
    painter.fillRect(image.rect(), sky)
    painter.drawImage(QPoint(0, 0), shot)
    painter.end()
    return image


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("out_dir", nargs="?", default=".")
    parser.add_argument("--backdrop", type=int, default=85)
    parser.add_argument("--font", type=int, default=17)
    parser.add_argument("--lang", default="en", choices=["en", "zh", "vi"])
    parser.add_argument("--hide-bars", action="store_true")
    args = parser.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)
    app.setStyleSheet(theme.style_sheet())
    settings = Settings(backdrop=args.backdrop, font_px=args.font, ui_lang=args.lang)
    window = MainWindow(DemoBackend(), settings, save=lambda s: None)
    wrist = attach_wrist(window)
    # the offscreen platform has no fonts, so the real one is used without showing anything
    window.setAttribute(Qt.WA_DontShowOnScreen)
    window.show_status(Status("warn", "Demo", ""))
    for number, (who, lang, texts) in enumerate(SCRIPT, 1):
        mine = who == 0
        src, dst = ("vi", "zh") if mine else (lang, "vi")
        window.show_utterance(Utterance(
            id=number, source="mic" if mine else "speaker", speaker=who, original=texts[src],
            translation=texts[dst], src_lang=src, dst_lang=dst, final=True,
            latency_ms=700 + 90 * number, sent=True if mine else None))
    window.show_utterance(Utterance(id=99, source="speaker", speaker=2, original="Wait, I think",
                                    src_lang="en", dst_lang="vi"))
    window.mic_bar.set_level(0.3)
    window.speaker_bar.set_level(0.7)
    window.show()
    if args.hide_bars:
        window._show_bars(False)
    app.processEvents()
    window.log.verticalScrollBar().setValue(window.log.verticalScrollBar().maximum())
    app.processEvents()
    over_game(window).save(str(out / "main.png"))

    window._dialog = dialog = SettingsWindow(settings, window)
    dialog.setAttribute(Qt.WA_DontShowOnScreen)
    dialog.show()
    for page in range(dialog.pages.count()):
        dialog.nav.setCurrentRow(page)
        app.processEvents()
        dialog.grab().save(str(out / f"settings_{page}.png"))
    print("saved to", out.resolve())


if __name__ == "__main__":
    main()
