"""The wrist display's own settings window (the "VR" button in the title bar opens it):
left — a dark arm preview you can orbit with the mouse; right — look / place controls and a
close-up of the overlay."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (QComboBox, QDialog, QFrame, QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QSlider, QVBoxLayout, QWidget)

from ui.i18n import tr
from ui.settings_window import SettingsWindow, select_data
from ui.widgets import Switch

from . import config
from .arm_preview import ArmPreview
from .config import VrSettings
from .display import WristDisplay
from .demo import DemoPanel

PREVIEW_WIDTH = 440
PLACE = ("along_cm", "out_cm", "up_cm", "tilt_deg", "yaw_deg", "roll_deg")


class VrDialog(QDialog):
    def __init__(self, display: WristDisplay, parent=None):
        super().__init__(parent)
        self.display = display
        self.settings = display.settings
        self._switches: dict[str, Switch] = {}
        self._sliders: dict[str, tuple[QSlider, QLabel, str]] = {}
        self._filling = False
        self._preview_look = None
        self.setObjectName("settings")
        self.setWindowTitle(tr("Wrist display (SteamVR)"))
        self.resize(980, 760)

        # ---- left: arm placement preview --------------------------------
        left = QWidget()
        left.setMaximumWidth(408)
        left_col = QVBoxLayout(left)
        left_col.setContentsMargins(18, 18, 10, 18)
        left_col.setSpacing(8)
        place_title = QLabel(tr("On the arm"))
        place_title.setObjectName("heading")
        self.arm_hint = QLabel(tr("Drag to rotate. Scroll to zoom. Place controls move the overlay."))
        self.arm_hint.setObjectName("dim")
        self.arm_hint.setWordWrap(True)
        self.arm = ArmPreview()
        self.arm.setFixedHeight(340)
        self.arm.setAccessibleName(tr("The panel on the arm"))
        left_col.addWidget(place_title)
        left_col.addWidget(self.arm_hint)
        left_col.addWidget(self.arm)
        credit = QLabel(tr("Hand model by {author}").format(author="omoideshabou"))
        credit.setObjectName("dim")
        left_col.addWidget(credit)
        left_col.addStretch(1)

        # ---- right: customize overlay -----------------------------------
        right_page = QWidget()
        outer = QVBoxLayout(right_page)
        outer.setContentsMargins(10, 18, 22, 18)
        outer.setSpacing(12)
        heading = QLabel(tr("Wrist display (SteamVR)"))
        heading.setObjectName("heading")
        self.state = QLabel()
        self.state.setObjectName("dim")
        self.state.setWordWrap(True)
        style_title = QLabel(tr("Overlay"))
        style_title.setObjectName("title")
        self.preview_panel = DemoPanel(self.settings)
        self.preview = QGraphicsView()
        scene = QGraphicsScene(self.preview)
        self.preview.setScene(scene)
        self._preview_proxy = scene.addWidget(self.preview_panel)
        self.preview.setSceneRect(self.preview_panel.rect())
        self.preview.setFrameShape(QFrame.NoFrame)
        self.preview.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.preview.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.preview.setStyleSheet("background: transparent; border: none;")
        self.preview.setRenderHint(QPainter.SmoothPixmapTransform)
        self.preview.setFixedSize(PREVIEW_WIDTH, round(PREVIEW_WIDTH * 480 / 720))
        self.preview.scale(PREVIEW_WIDTH / 720, PREVIEW_WIDTH / 720)
        self.preview.setAccessibleName(tr("The panel as it looks now"))
        outer.addWidget(heading)
        outer.addWidget(self.state)
        help_text = QLabel(tr("Look at the wrist panel, point with your other controller, then press and "
                              "release the trigger. Use the thumbstick to scroll.") + " " +
                           tr("Hold the trigger on the scrollbar to drag it."))
        help_text.setObjectName("dim")
        help_text.setWordWrap(True)
        outer.addWidget(help_text)
        outer.addWidget(style_title)
        outer.addWidget(self.preview, 0, Qt.AlignHCenter)
        preview_hint = QLabel(tr("Click the icons and use the mouse wheel to scroll. This demo does not change live capture."))
        preview_hint.setObjectName("dim")
        preview_hint.setWordWrap(True)
        outer.addWidget(preview_hint)

        self.hand = QComboBox()
        for code, name in config.HANDS.items():
            self.hand.addItem(tr(name), code)
        self.hand.currentIndexChanged.connect(lambda: self._set("hand", self.hand.currentData()))
        reset = QPushButton(tr("Reset"))
        reset.setObjectName("plain")
        reset.setCursor(Qt.PointingHandCursor)
        reset.clicked.connect(self.reset_place)
        card = SettingsWindow._card
        outer.addWidget(card([
            ("Show on my wrist", "The chat log follows your hand in SteamVR. It connects by "
                                 "itself whenever SteamVR is running.", self._switch("enabled")),
            ("Hand", "The controller that carries the panel.", self.hand),
            ("Only when I look at it", "The panel fades in when you turn your wrist towards "
                                       "your face, like checking a watch.", self._switch("look_only")),
        ]))
        for title, rows in (
            ("Look", [
                ("Size", "How wide the panel is.", self._slider("width_cm", config.WIDTH_RANGE, " cm")),
                ("Text size", "", self._slider("font_px", config.FONT_RANGE, " px")),
                ("Opacity", "How solid the whole panel is.", self._slider("opacity", config.OPACITY_RANGE, "%")),
                ("Background darkness", "0% leaves only the letters.",
                 self._slider("backdrop", config.BACKDROP_RANGE, "%")),
            ]),
            ("Place", [
                ("Along the arm", "From the hand towards the elbow.",
                 self._slider("along_cm", config.ALONG_RANGE, " cm")),
                ("Away from the arm", "", self._slider("out_cm", config.OUT_RANGE, " cm")),
                ("Up / down", "", self._slider("up_cm", config.UP_RANGE, " cm")),
                ("Turn around the wrist", "Use this when the panel faces the wrong way.",
                 self._slider("tilt_deg", config.TILT_RANGE, "°")),
                ("Tilt toward fingers", "Angle the panel toward your fingers or elbow.",
                 self._slider("yaw_deg", config.ROTATION_RANGE, "°")),
                ("Rotate text", "Turn the text sideways or upside down.",
                 self._slider("roll_deg", config.ROTATION_RANGE, "°")),
                ("Back to the starting place", "", reset),
            ]),
        ):
            label = QLabel(tr(title))
            label.setObjectName("title")
            outer.addSpacing(6)
            outer.addWidget(label)
            outer.addWidget(card(rows))
        outer.addStretch(1)

        scroll = QScrollArea()
        scroll.setObjectName("page")
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea#page, QScrollArea#page > QWidget > QWidget "
                             "{ background: transparent; }")
        scroll.setWidget(right_page)
        right_page.ensurePolished()
        # Horizontal scrolling is hidden, so reserve the full page width plus its scrollbar.
        scroll.setMinimumWidth(right_page.minimumSizeHint().width()
                               + scroll.verticalScrollBar().sizeHint().width() + 2 * scroll.frameWidth())

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(left, 1)
        root.addWidget(scroll, 1)
        self.setMinimumSize(root.minimumSize().width(), max(600, root.minimumSize().height()))

        # Coalesce changes into the next frame without waiting for slider movement to stop.
        self._redraw = QTimer(self)
        self._redraw.setSingleShot(True)
        self._redraw.setInterval(16)
        self._redraw.timeout.connect(self.show_preview)
        self.preview_panel.changed.connect(self._panel_changed)
        display.state_changed.connect(self.show_state)
        self.sync()
        self.show_state()
        self.show_preview()

    # ---- controls -------------------------------------------------------

    def _switch(self, name: str) -> Switch:
        switch = Switch()
        switch.toggled.connect(lambda on: self._set(name, on))
        self._switches[name] = switch
        return switch

    def _slider(self, name: str, limits: tuple[int, int], unit: str) -> QWidget:
        slider = QSlider(Qt.Horizontal)
        slider.setRange(*limits)
        slider.setFixedWidth(170)
        value = QLabel()
        value.setFixedWidth(48)
        value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._sliders[name] = (slider, value, unit)

        def moved(number: int) -> None:
            value.setText(f"{number}{unit}")
            self._set(name, number)
        slider.valueChanged.connect(moved)
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(slider)
        row.addWidget(value)
        return box

    def _set(self, name: str, value) -> None:
        if self._filling or getattr(self.settings, name) == value:
            return
        setattr(self.settings, name, value)
        self.display.settings_changed()
        self._panel_changed()

    def sync(self) -> None:
        """Put the saved settings into the controls."""
        self._filling = True
        for name, switch in self._switches.items():
            switch.setChecked(getattr(self.settings, name))
        for name, (slider, value, unit) in self._sliders.items():
            slider.setValue(getattr(self.settings, name))
            value.setText(f"{slider.value()}{unit}")
        select_data(self.hand, self.settings.hand)
        self._filling = False

    def reset_place(self) -> None:
        defaults = VrSettings()
        for name in PLACE:
            setattr(self.settings, name, getattr(defaults, name))
        self.sync()
        self.display.settings_changed()
        self.show_preview()

    # ---- what it reports ------------------------------------------------

    def show_state(self, _state: str = "") -> None:
        text = tr(self.display.state)
        if self.display.problem:
            text += f" ({self.display.problem})"
        self.state.setText(text)

    def _panel_changed(self) -> None:
        if self.isVisible() and not self._redraw.isActive():
            self._redraw.start()

    def show_preview(self) -> None:
        look = (self.settings.font_px, self.display.panel.log._look[1], self.settings.backdrop)
        if look != self._preview_look:
            self._preview_look = look
            self.preview_panel.set_look(*look)
        self._preview_proxy.setOpacity(self.settings.opacity / 100)
        self.arm.set_scene(self.settings, self.preview_panel.image())

    def showEvent(self, event):
        super().showEvent(event)
        self.show_state()
        self.show_preview()
