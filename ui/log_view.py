"""The chat log: one row per spoken or typed line, newest at the bottom."""
from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsDropShadowEffect, QLabel, QScrollArea, QVBoxLayout,
                               QWidget)

from . import theme
from .backend import LANGS, OTHER_LANGS, Utterance
from .i18n import tr, tr_note

MAX_ROWS = 200
FLOATING_DIM = "#d9d9e3"   # the small grey text, lighter when there is no background behind it
SHORT = {"en": "EN", "zh": "ZH", "vi": "VI", "yue": "ZH(HK)", "ja": "JA", "ko": "KO"}


class SelectableText(QLabel):
    """Keep click-to-copy while letting Qt handle partial text selection."""

    def __init__(self, row):
        super().__init__(row)
        self.row = row
        self._press_position = None
        self.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.setCursor(Qt.IBeamCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_position = event.position().toPoint()
        super().mousePressEvent(event)
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_position = event.position().toPoint()
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton and self._press_position is not None:
            distance = (event.position().toPoint() - self._press_position).manhattanLength()
            self._press_position = None
            if self.hasSelectedText():
                self.row.copy_text(self.selectedText())
            elif distance < QApplication.startDragDistance():
                self.row.copy_text(self.row.main_text())
        event.accept()


class LogRow(QFrame):
    def __init__(self, utterance: Utterance, parent=None):
        super().__init__(parent)
        self.utterance = utterance
        self._font_px = 17
        self._show_original = True
        self._shadow = False
        self._copied = False
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("LogRow { background: transparent; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 6)
        layout.setSpacing(1)
        self.header = QLabel()
        self.original = SelectableText(self)
        self.translation = SelectableText(self)
        self.translation2 = SelectableText(self)
        self.header.setAttribute(Qt.WA_TransparentForMouseEvents)
        for label in (self.header, self.original, self.translation, self.translation2):
            label.setWordWrap(True)
            label.setTextFormat(Qt.RichText)
            layout.addWidget(label)
        self.refresh()

    def set_utterance(self, utterance: Utterance) -> None:
        self.utterance = utterance
        self.refresh()

    def set_look(self, font_px: int, show_original: bool, shadow: bool) -> None:
        self._font_px, self._show_original, self._shadow = font_px, show_original, shadow
        self.refresh()

    def other_language(self) -> str:
        """"【Speaking Spanish】" for another player's finished line in a language the app does
        not translate; "" for every other line. (The engine only reports such a language when
        it is at least 80% sure; below that it treats the line as one of ours.)"""
        u = self.utterance
        if not (u.final and u.source == "speaker" and u.src_lang) or u.src_lang in LANGS:
            return ""
        name = tr(OTHER_LANGS[u.src_lang]) if u.src_lang in OTHER_LANGS else u.src_lang.upper()
        return tr("【Speaking {lang}】").format(lang=name)

    def main_text(self) -> str:
        """What a click copies: what was said (the original text), or the translation when a
        line has no original."""
        return self.other_language() or self.utterance.original or self.utterance.translation

    def refresh(self) -> None:
        u = self.utterance
        mine = u.source in ("mic", "typed")
        dim = FLOATING_DIM if self._shadow else theme.DIM
        self.setToolTip(tr("Click to copy the original text. Drag to select and copy only that text."))
        name = tr("You") if mine else (tr("Speaker {n}").format(n=u.speaker) if u.speaker
                                       else tr("Speaker"))
        color = theme.ACCENT if mine else theme.speaker_color(u.speaker)
        meta = []
        other = self.other_language()
        if u.src_lang and u.dst_lang and u.src_lang != u.dst_lang and not other:
            meta.append(f"{SHORT.get(u.src_lang, u.src_lang)} → {SHORT.get(u.dst_lang, u.dst_lang)}")
        if u.translation2:
            meta.append(SHORT.get(u.dst_lang2, u.dst_lang2))
        if u.source == "typed":
            meta.append(tr("typed"))
        # the delay and "sent to chatbox" were shown while testing; engine.log still has the delay.
        # A failed send is still worth seeing.
        if mine and u.final and u.sent is False:
            meta.append(f'<span style="color:{theme.ERROR}">{tr("not sent")}</span>')
        if u.note:
            meta.append(escape(tr_note(u.note)))
        if self._copied:
            meta.append(f'<span style="color:{theme.OK}">{tr("copied")}</span>')
        small = max(self._font_px - 6, 10)
        self.header.setText(
            f'<span style="color:{color}; font-weight:600; font-size:{small + 1}px">{name}</span>'
            f'<span style="color:{dim}; font-size:{small}px">&nbsp;&nbsp;{" · ".join(meta)}</span>')

        translated = bool(u.translation) and u.src_lang != u.dst_lang
        if other:
            # not one of our languages: say which one it was instead of guessing at the words
            self.original.setText(self._span(other, dim, self._font_px, italic=True))
            self.original.setVisible(True)
            self.translation.setVisible(False)
        elif not u.final:
            # still talking: the heard text grows, the translation comes after
            self.original.setText(self._span(u.original or "…", theme.TEXT, self._font_px))
            self.original.setVisible(True)
            waiting = tr("translating…" if u.source == "typed" else "listening…")
            self.translation.setText(self._span(waiting, dim, small + 1, italic=True))
            self.translation.setVisible(True)
        elif translated:
            self.original.setText(self._span(u.original, dim, max(self._font_px - 3, 11)))
            self.original.setVisible(self._show_original and bool(u.original))
            self.translation.setText(self._span(u.translation, theme.TEXT, self._font_px))
            self.translation.setVisible(True)
        else:
            self.original.setText(self._span(u.original, theme.TEXT, self._font_px))
            self.original.setVisible(True)
            self.translation.setVisible(False)
        self.translation2.setText(self._span(u.translation2, theme.TEXT, self._font_px))
        self.translation2.setVisible(bool(u.final and u.translation2 and not other))
        self._shade_letters(self._shadow)

    def _shade_letters(self, on: bool) -> None:
        """With a see-through window only the letters are drawn, no box behind the row. A dark
        shadow under each letter keeps them readable over a bright game, like film subtitles."""
        if on == (self.graphicsEffect() is not None):
            return
        if not on:
            self.setGraphicsEffect(None)
            return
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(5)
        shadow.setOffset(1, 1)
        shadow.setColor(QColor(0, 0, 0, 255))
        self.setGraphicsEffect(shadow)

    @staticmethod
    def _span(text: str, color: str, px: int, italic: bool = False) -> str:
        style = f"color:{color}; font-size:{px}px" + ("; font-style:italic" if italic else "")
        return f'<span style="{style}">{escape(text)}</span>'

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.main_text():
            self.copy_text(self.main_text())
        super().mousePressEvent(event)

    def copy_text(self, text):
        if not text:
            return
        QGuiApplication.clipboard().setText(text)
        self._copied = True
        self.refresh()
        QTimer.singleShot(1200, self._uncopy)

    def _uncopy(self):
        self._copied = False
        self.refresh()


class LogView(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self.viewport().setAutoFillBackground(False)
        self._body = QWidget()
        self._layout = QVBoxLayout(self._body)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(4)
        self._layout.addStretch(1)   # keeps the rows at the bottom, like subtitles
        self.setWidget(self._body)
        self._rows: dict[int, LogRow] = {}
        self._look = (17, True, False)
        self._stick = True
        bar = self.verticalScrollBar()
        bar.valueChanged.connect(self._moved)
        bar.rangeChanged.connect(self._grew)

    def rows(self) -> list[LogRow]:
        return list(self._rows.values())

    def add_or_update(self, utterance: Utterance) -> LogRow:
        row = self._rows.get(utterance.id)
        if row:
            row.set_utterance(utterance)
            return row
        row = LogRow(utterance)
        row.set_look(*self._look)
        self._rows[utterance.id] = row
        self._layout.addWidget(row)
        while len(self._rows) > MAX_ROWS:
            oldest = next(iter(self._rows))
            self._rows.pop(oldest).deleteLater()
        return row

    def clear(self) -> None:
        for row in self._rows.values():
            row.deleteLater()
        self._rows.clear()

    def set_look(self, font_px: int, show_original: bool, shadow: bool) -> None:
        self._look = (font_px, show_original, shadow)
        for row in self._rows.values():
            row.set_look(*self._look)

    def refresh(self) -> None:
        """Redraw every row (after the window's language changed)."""
        for row in self._rows.values():
            row.refresh()

    # stay at the newest line unless the user scrolled up to read older ones
    def _moved(self, value: int) -> None:
        self._stick = value >= self.verticalScrollBar().maximum() - 4

    def _grew(self, _low: int, high: int) -> None:
        if self._stick:
            self.verticalScrollBar().setValue(high)
