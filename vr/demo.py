"""An interactive desktop copy of the wrist panel, with example conversation only."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from ui import i18n
from ui.backend import Backend, Status, Utterance
from ui.demo_backend import SCRIPT
from ui.i18n import tr

from .config import VrSettings
from .panel import WristPanel


class DemoPanel(WristPanel):
    def __init__(self, settings: VrSettings):
        backend = Backend()
        super().__init__(backend)
        self.backend = backend
        backend.setParent(self)
        self.setWindowFlags(Qt.Widget)
        self.setAttribute(Qt.WA_DontShowOnScreen, False)
        self.set_look(settings.font_px, True, settings.backdrop)
        self.toggle_requested.connect(self._toggle)
        self.swap_requested.connect(self._swap_demo_languages)
        self.set_languages(["vi"], ["en"])
        self.backend.status_changed.emit(Status("ok", "Demo", ""))
        for number, (who, language, texts) in enumerate(SCRIPT * 2):
            src = language or "vi"
            dst = i18n.lang()
            self.backend.utterance.emit(Utterance(
                number, "mic" if who == 0 else "speaker", speaker=who,
                original=texts[src], translation=texts[dst] if src != dst else "",
                src_lang=src, dst_lang=dst, final=True))

    def _toggle(self, name: str) -> None:
        mic, subtitles = self._switches
        self.set_switches(not mic if name == "mic_on" else mic,
                          not subtitles if name == "subtitles_on" else subtitles)

    def _swap_demo_languages(self) -> None:
        mine, theirs = self._languages
        if self.swap.isEnabled():
            self.set_languages(theirs, mine)


class WristDemo(QDialog):
    def __init__(self, settings: VrSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Wrist controls demo"))
        self.setObjectName("settings")
        self.panel = DemoPanel(settings)
        layout = QVBoxLayout(self)
        hint = QLabel(tr("Click the icons and use the mouse wheel to scroll. This demo does not change live capture."))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addWidget(self.panel)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)


def main() -> int:
    """Open the desktop demo without starting capture or connecting to SteamVR."""
    import sys

    from PySide6.QtWidgets import QApplication
    from ui import config as ui_config, theme
    from . import config

    app = QApplication(sys.argv)
    i18n.set_lang(ui_config.load().ui_lang)
    app.setStyleSheet(theme.style_sheet())
    demo = WristDemo(config.load())
    demo.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
