"""The picture on the wrist: the status line and the chat log, drawn without ever being shown
on the desktop. It is an ordinary widget (the same chat log as the window's), so everything
the window can show, the wrist shows the same way."""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QGridLayout, QHBoxLayout, QLabel, QSizePolicy,
                               QStyle, QStyleOptionSlider, QToolButton, QVBoxLayout, QWidget)

from ui import theme
from ui.backend import AUTO, LANGS, Backend, Status, Utterance
from ui.i18n import tr
from ui.log_view import SHORT, LogView

SIZE = (720, 480)      # px; SteamVR stretches it to the width chosen in the settings
SHADOW_BELOW = 50      # backdrop % under which the letters get a dark shadow, as in the window
CURSOR_SIZE = 16


@lru_cache(maxsize=2)
def cursor_image(held: bool) -> QImage:
    picture = QImage(CURSOR_SIZE, CURSOR_SIZE, QImage.Format_ARGB32_Premultiplied)
    picture.fill(Qt.transparent)
    painter = QPainter(picture)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor(theme.ACCENT), 3))
    painter.setBrush(QColor(theme.ACCENT if held else theme.TEXT))
    painter.drawEllipse(QPointF(CURSOR_SIZE / 2, CURSOR_SIZE / 2), 6, 6)
    painter.end()
    return picture.convertToFormat(QImage.Format_RGBA8888)


class WristPanel(QWidget):
    changed = Signal()     # it would look different if drawn again
    interaction_changed = Signal()  # input feedback is sent immediately, without the text debounce
    toggle_requested = Signal(str)
    languages_requested = Signal(str, list)
    swap_requested = Signal()

    def __init__(self, backend: Backend):
        super().__init__()
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DontShowOnScreen)      # laid out like a shown window, never seen
        self.setFixedSize(*SIZE)
        self.setStyleSheet("QToolButton { font-size: 18px; padding: 4px 8px; } "
                           "QToolButton:checked { background: rgba(90,184,255,35); } "
                           "QToolButton:pressed { background: rgba(90,184,255,90); } "
                           f"QToolButton#language {{ background: {theme.PANEL_HI}; font-size: 16px; }}")
        self._backdrop = 80
        self._status = Status("warn", "Starting…", "")
        self._switches = (True, True)
        self._pointer: QPoint | None = None
        self._held = False
        self._pressed_button = None
        self._scroll_drag_offset: int | None = None
        self._tips = []
        self._languages = (["vi"], [AUTO])
        self._picking_language: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 12)
        root.setSpacing(4)
        head = QHBoxLayout()
        head.setContentsMargins(6, 0, 6, 0)
        head.setSpacing(8)
        self.dot = QLabel()
        self.status = QLabel()
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.my_lang = self._button(None, "I", lambda: self._open_languages("my_lang"))
        self.their_lang = self._button(None, "They", lambda: self._open_languages("their_lang"))
        for button in (self.my_lang, self.their_lang):
            button.setObjectName("language")
        self.swap = self._button("swap", "Swap the two languages", self.swap_requested.emit)
        self.mic = self._button("mic", "My mic → chatbox", lambda: self.toggle_requested.emit("mic_on"))
        self.speaker = self._button("speaker", "Other players → subtitles",
                                    lambda: self.toggle_requested.emit("subtitles_on"))
        head.addWidget(self.dot, 0, Qt.AlignVCenter)
        head.addWidget(self.status, 1)
        head.addWidget(self.my_lang)
        head.addWidget(self.swap)
        head.addWidget(self.their_lang)
        head.addWidget(self.mic)
        head.addWidget(self.speaker)
        self.log = LogView()
        self.log.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # nothing behind the rows but the panel's own plate, whatever the program's style says
        self.log.setStyleSheet(
            "QScrollArea, QScrollArea > QWidget > QWidget "
            "{ background: transparent; border: none; }"
            f"QScrollBar:vertical {{ background: {theme.PANEL_HI}; width: 8px; margin: 1px; border-radius: 3px; }}"
            f"QScrollBar::handle:vertical {{ background: {theme.ACCENT}; border-radius: 3px; min-height: 40px; }}"
            f"QScrollBar::handle:vertical:hover {{ background: {theme.ACCENT_HOVER}; }}")
        root.addLayout(head)
        # Keep choices inside the rendered panel so the VR pointer can select them.
        self.language_menu = QWidget()
        choices = QGridLayout(self.language_menu)
        choices.setContentsMargins(0, 0, 0, 0)
        self.language_choices = {}
        for index, (code, name) in enumerate([*LANGS.items(), (AUTO, "Auto")]):
            button = self._button(None, name, lambda _checked=False, code=code: self._pick_language(code))
            button.setCheckable(True)
            choices.addWidget(button, index // 4, index % 4)
            self.language_choices[code] = button
        self.language_done = self._button(None, "Done", self._close_languages)
        choices.addWidget(self.language_done, 1, 3)
        self.language_hint = QLabel(tr("Choose up to 3 languages. Tap a selected language to remove it."))
        self.language_hint.setWordWrap(True)
        choices.addWidget(self.language_hint, 2, 0, 1, 4)
        self.language_menu.hide()
        root.addWidget(self.language_menu)
        root.addWidget(self.log, 1)
        self.log.verticalScrollBar().valueChanged.connect(lambda _value: self.changed.emit())

        backend.status_changed.connect(self.show_status)
        backend.utterance.connect(self.show_utterance)
        self.set_look(24, True, 80)
        self.set_switches(True, True)
        self.retranslate()
        self.show()

    def _button(self, icon, text, callback):
        button = QToolButton()
        button.setMinimumSize(44, 44)
        if icon:
            button.setIcon(theme.icon(icon, size=26))
            button.setIconSize(QSize(26, 26))
        else:
            button.setText(tr(text))
        button.clicked.connect(callback)
        self._tips.append((button, text, icon))
        return button

    def scroll(self, pixels: int) -> None:
        bar = self.log.verticalScrollBar()
        bar.setValue(bar.value() + pixels)
        self.interaction_changed.emit()

    def set_languages(self, mine: list[str], theirs: list[str]) -> None:
        self._languages = (list(mine), list(theirs))
        for button, label, codes in ((self.my_lang, "I", mine), (self.their_lang, "They", theirs)):
            name = " + ".join(tr("Auto") if code == AUTO else SHORT.get(code, code) for code in codes)
            button.setText(f"{tr(label)}  {name} ▾")
            button.ensurePolished()
            button.setFixedWidth(max(44, button.fontMetrics().horizontalAdvance(button.text()) + 24))
            description = f"{tr(label)}: " + " + ".join(
                tr("Auto") if code == AUTO else tr(LANGS.get(code, code)) for code in codes)
            button.setToolTip(description)
            button.setAccessibleName(description)
        self.swap.setEnabled(AUTO not in theirs)
        selected = mine if self._picking_language == "my_lang" else theirs
        for code, button in self.language_choices.items():
            button.setChecked(code in selected)
            button.setEnabled(len(selected) < 3 or code in selected or code == AUTO)
        self.changed.emit()

    def _open_languages(self, name: str) -> None:
        if self._picking_language == name:
            self._close_languages()
            return
        self._picking_language = name
        self.language_choices[AUTO].setVisible(name == "their_lang")
        self.set_languages(*self._languages)
        self.language_menu.show()
        self.interaction_changed.emit()
        self.changed.emit()

    def _close_languages(self) -> None:
        if self._picking_language is not None:
            self._picking_language = None
            self.language_menu.hide()
            self.interaction_changed.emit()
            self.changed.emit()

    def _pick_language(self, code: str) -> None:
        name = self._picking_language
        if name is None or code not in self.language_choices:
            return
        mine, theirs = self._languages
        selected = list(mine if name == "my_lang" else theirs)
        if code == AUTO:
            if name != "their_lang":
                return
            selected = [AUTO]
        elif code in selected:
            if len(selected) == 1 and name == "my_lang":
                self.set_languages(mine, theirs)  # keep at least one microphone language checked
                return
            selected.remove(code)
            selected = selected or [AUTO]
        elif len(selected) < 3:
            selected = [value for value in selected if value != AUTO] + [code]
        else:
            return
        self.set_languages(selected if name == "my_lang" else mine,
                           selected if name == "their_lang" else theirs)
        self.languages_requested.emit("my_languages" if name == "my_lang" else "their_languages", selected)
        self.interaction_changed.emit()

    def point(self, uv: tuple[float, float] | None, held: bool = False) -> None:
        """Select buttons on release or drag the scrollbar while held; leaving cancels."""
        point = QPoint(int(uv[0] * self.width()), int(uv[1] * self.height())) if uv is not None else None
        bar = self.log.verticalScrollBar()
        old_scroll = bar.value()
        if point is None or not held or not bar.isVisible() or bar.maximum() <= bar.minimum():
            self._scroll_drag_offset = None
        else:
            local = bar.mapFrom(self, point)
            option = QStyleOptionSlider()
            bar.initStyleOption(option)
            handle = bar.style().subControlRect(QStyle.CC_ScrollBar, option, QStyle.SC_ScrollBarSlider, bar)
            groove = bar.style().subControlRect(QStyle.CC_ScrollBar, option, QStyle.SC_ScrollBarGroove, bar)
            # Keep a forgiving controller target around the thin visible scrollbar.
            if not self._held and bar.rect().adjusted(-8, 0, 8, 0).contains(local):
                self._scroll_drag_offset = (local.y() - handle.top()
                                            if handle.top() <= local.y() <= handle.bottom()
                                            else handle.height() // 2)
            if self._scroll_drag_offset is not None:
                span = max(0, groove.height() - handle.height())
                position = max(0, min(span, local.y() - groove.top() - self._scroll_drag_offset))
                bar.setValue(QStyle.sliderValueFromPosition(
                    bar.minimum(), bar.maximum(), position, span, option.upsideDown))
        previous = self._pressed_button
        was_down = previous.isDown() if previous is not None else False
        self._pointer = point
        target = self.childAt(point) if point is not None else None
        while target is not None and target is not self and not isinstance(target, QAbstractButton):
            target = target.parentWidget()
        if not isinstance(target, QAbstractButton) or not target.isEnabled():
            target = None
        if point is None:
            self._close_languages()
            if self._pressed_button is not None:
                self._pressed_button.setDown(False)
            self._pressed_button = None
        elif held and not self._held:
            self._pressed_button = target
        if self._pressed_button is not None:
            self._pressed_button.setDown(held and target is self._pressed_button)
        if not held and self._held:
            pressed, self._pressed_button = self._pressed_button, None
            if pressed is not None and pressed is target:
                pressed.click()
        changed = (held != self._held or bar.value() != old_scroll
                   or (previous is not None and previous.isDown() != was_down))
        self._held = held
        if changed:
            self.interaction_changed.emit()

    @property
    def pointer(self):
        uv = (self._pointer.x() / self.width(), self._pointer.y() / self.height()) if self._pointer is not None else None
        return uv, self._held

    # ---- what it shows --------------------------------------------------

    def show_status(self, status: Status) -> None:
        if (status.level, status.text) == (self._status.level, self._status.text) and self.status.text():
            return
        self._status = status
        color = theme.STATUS_COLORS.get(status.level, theme.WARN)
        size = self.dot.width()
        self.dot.setStyleSheet(f"background: {color}; border-radius: {size // 2}px;")
        self.status.setText(tr(status.text))
        self.changed.emit()

    def show_utterance(self, utterance: Utterance) -> None:
        self.log.add_or_update(utterance)
        self.changed.emit()

    def set_switches(self, mic_on: bool, subtitles_on: bool) -> None:
        """The two small icons on the right: is my mic translated, are other players."""
        self._switches = (mic_on, subtitles_on)
        size = 26
        for button, name, on in ((self.mic, "mic", mic_on), (self.speaker, "speaker", subtitles_on)):
            icon = theme.icon(name if on else name + "_off", theme.TEXT if on else theme.ERROR, size)
            button.setIcon(icon)
            button.setCheckable(True)
            button.setChecked(on)
        self.changed.emit()

    def set_look(self, font_px: int, show_original: bool, backdrop: int) -> None:
        self._backdrop = backdrop
        small = max(font_px - 6, 12)
        self.dot.setFixedSize(small - 2, small - 2)
        self.status.setStyleSheet(f"color: {theme.DIM}; font-size: {small}px;")
        self.log.set_look(font_px, show_original, backdrop < SHADOW_BELOW)
        status, self._status = self._status, Status("", "", "")    # drawn again at the new size
        self.show_status(status)
        self.set_switches(*self._switches)
        self.update()

    def retranslate(self) -> None:
        """After the window's language changed."""
        self.status.setText(tr(self._status.text))
        for button, text, icon in self._tips:
            button.setToolTip(tr(text))
            button.setAccessibleName(tr(text))
            if not icon:
                button.setText(tr(text))
        self.set_languages(*self._languages)
        self.language_hint.setText(tr("Choose up to 3 languages. Tap a selected language to remove it."))
        self.log.refresh()
        self.changed.emit()

    # ---- drawing --------------------------------------------------------

    def paintEvent(self, event):
        alpha = round(255 * self._backdrop / 100)
        if not alpha:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(11, 11, 13, alpha))
        painter.setPen(QPen(QColor(255, 255, 255, 40)))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 18, 18)

    def image(self, include_pointer: bool = True) -> QImage:
        """The panel as it looks now, see-through where nothing is drawn."""
        picture = QImage(self.size(), QImage.Format_ARGB32_Premultiplied)
        picture.fill(Qt.transparent)
        self.render(picture)
        if include_pointer and self._pointer is not None:
            painter = QPainter(picture)
            painter.drawImage(self._pointer - QPoint(CURSOR_SIZE // 2, CURSOR_SIZE // 2), cursor_image(self._held))
            painter.end()
        return picture.convertToFormat(QImage.Format_RGBA8888)


def rgba(picture: QImage) -> bytes:
    """The picture's bytes as SteamVR takes them (4 a pixel, top row first)."""
    return bytes(picture.constBits())[:picture.width() * picture.height() * 4]
