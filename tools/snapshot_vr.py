"""Draw the wrist panel and its settings to PNG files, to check the look without a headset.

    python tools/snapshot_vr.py [out_dir] [--font N] [--backdrop N] [--lang en|zh|vi]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from tools.snapshot_ui import over_game  # noqa: E402
from ui import i18n, theme  # noqa: E402
from ui.backend import Backend, Status, Utterance  # noqa: E402
from ui.demo_backend import SCRIPT  # noqa: E402
from vr.config import VrSettings  # noqa: E402
from vr.display import WristDisplay  # noqa: E402
from vr.demo import WristDemo  # noqa: E402
from vr.panel import WristPanel  # noqa: E402
from vr.settings_dialog import VrDialog  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("out_dir", nargs="?", default=".")
    parser.add_argument("--font", type=int, default=24)
    parser.add_argument("--backdrop", type=int, default=80)
    parser.add_argument("--lang", default="en", choices=["en", "zh", "vi"])
    args = parser.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)
    panel, wrist = demo_panel(app, VrSettings(font_px=args.font, backdrop=args.backdrop), args.lang)
    panel.image().save(str(out / "wrist.png"))
    over_game(panel).save(str(out / "wrist_over_game.png"))

    dialog = VrDialog(wrist)
    dialog.setAttribute(Qt.WA_DontShowOnScreen)
    dialog.show()
    app.processEvents()
    dialog.grab().save(str(out / "wrist_settings.png"))
    dialog.resize(dialog.minimumSize())
    app.processEvents()
    dialog.grab().save(str(out / "wrist_settings_minimum.png"))
    demo = WristDemo(wrist.settings)
    demo.setAttribute(Qt.WA_DontShowOnScreen)
    demo.show()
    app.processEvents()
    demo.grab().save(str(out / "wrist_controls.png"))
    demo.panel.their_lang.click()
    demo.panel.language_choices["ja"].click()
    app.processEvents()
    demo.grab().save(str(out / "wrist_languages.png"))
    print("saved to", out.resolve())


def demo_panel(app, settings: VrSettings, lang: str = "en"):
    """The wrist panel filled with the demo's example lines (also used by preview_wrist.py)."""
    app.setStyleSheet(theme.style_sheet())
    i18n.set_lang(lang)
    backend = Backend()
    panel = WristPanel(backend)
    wrist = WristDisplay(panel, settings, save=lambda s: None, running=lambda: False)
    wrist.tick()
    backend.status_changed.emit(Status("ok", "Listening", ""))
    for number, (who, lang, texts) in enumerate(SCRIPT, 1):
        mine = who == 0
        src, dst = ("vi", "zh") if mine else (lang, "vi")
        backend.utterance.emit(Utterance(
            id=number, source="mic" if mine else "speaker", speaker=who, original=texts[src],
            translation=texts[dst], src_lang=src, dst_lang=dst, final=True, sent=True if mine else None))
    backend.utterance.emit(Utterance(id=99, source="speaker", speaker=2, original="Wait, I think",
                                     src_lang="en", dst_lang="vi"))
    app.processEvents()
    app.processEvents()
    return panel, wrist


if __name__ == "__main__":
    main()
