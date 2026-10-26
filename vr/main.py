"""Connect the SteamVR wrist display to the main application and its shared settings."""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QToolButton

from ui import main as ui_main
from ui import theme
from ui.i18n import tr
from ui.main_window import MainWindow, TitleBar

from . import config, display
from .display import WristDisplay
from .panel import WristPanel
from .settings_dialog import VrDialog


def bind_wrist_controls(window: MainWindow, panel: WristPanel) -> None:
    """Use the desktop settings/save path so VR changes reach capture and both windows."""
    panel.toggle_requested.connect(window._flip)
    panel.swap_requested.connect(window._swap)

    def pick_languages(name: str, codes: list[str]) -> None:
        setattr(window.settings, name, list(codes))
        window.settings_changed()

    panel.languages_requested.connect(pick_languages)


def attach_wrist(window: MainWindow) -> WristDisplay:
    wrist = WristDisplay(WristPanel(window.backend), config.load(),
                         window_settings=lambda: window.settings)
    wrist.setParent(window)
    bind_wrist_controls(window, wrist.panel)
    add_vr_button(window, wrist)
    return wrist


def add_vr_button(window: MainWindow, wrist: WristDisplay) -> QToolButton:
    """A "VR" button left of the gear: it opens the wrist settings and is light blue while the
    panel is on the wrist."""
    button = QToolButton()
    button.setText("VR")
    button.setFixedWidth(36)
    button.setCursor(Qt.PointingHandCursor)
    dialog: list[VrDialog] = []

    def open_settings() -> None:
        if not dialog:
            dialog.append(VrDialog(wrist, window))
        dialog[0].sync()
        dialog[0].show()
        dialog[0].raise_()
        dialog[0].activateWindow()

    def show_state(state: str) -> None:
        color = {display.ON: theme.ACCENT, display.OFF: theme.DIM}.get(state, theme.TEXT)
        button.setStyleSheet(f"QToolButton {{ color: {color}; font-weight: 600; }}")
        tip = f"{tr('Wrist display (SteamVR)')}: {tr(state)}"
        button.setToolTip(tip)
        button.setAccessibleName(tip)

    def language_changed(_code: str) -> None:
        show_state(wrist.state)
        if dialog:
            old = dialog.pop()
            visible = old.isVisible()
            old.close()
            old.deleteLater()
            if visible:
                open_settings()

    button.clicked.connect(open_settings)
    wrist.state_changed.connect(show_state)
    wrist.language_changed.connect(language_changed)
    show_state(wrist.state)
    bar = window.findChild(TitleBar)
    row = window.title_buttons if bar else None
    if row is not None:
        row.insertWidget(max(row.count() - 4, 0), button)   # before gear, minimise, maximise, close
    else:                                # the window was rebuilt without a title bar: keep a way in
        button.setParent(window)
        button.move(8, 8)
    return button


def run(backend=None) -> int:
    return ui_main.run(backend)


if __name__ == "__main__":
    sys.exit(run())
