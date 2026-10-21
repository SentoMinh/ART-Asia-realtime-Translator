"""A language dropdown with up to three checked choices."""
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QComboBox, QStyle, QStyleOptionComboBox, QStylePainter

from .backend import AUTO, LANGS, PICK_LANGS
from .config import language_choices
from .i18n import tr

SHORT = {"en": "EN", "zh": "ZH", "yue": "YUE", "vi": "VI", "ja": "JA", "ko": "KO"}


class LanguagePicker(QComboBox):
    selection_changed = Signal(list)

    def __init__(self, with_auto=False, parent=None):
        super().__init__(parent)
        self.with_auto = with_auto
        self._selected = [AUTO] if with_auto else ["en"]
        self._updating = True
        for code in ([AUTO] if with_auto else []) + list(PICK_LANGS):
            self.addItem("", code)
        self._updating = False
        self.view().viewport().installEventFilter(self)
        self.view().installEventFilter(self)
        self.currentIndexChanged.connect(self._single_chosen)
        self.retranslate()

    def selected_codes(self):
        return list(self._selected)

    def currentText(self):
        if len(self._selected) == 1:
            code = self._selected[0]
            return tr("Auto-detect") if code == AUTO else tr(LANGS[code])
        return ", ".join(SHORT[code] for code in self._selected)

    def set_selected(self, codes, emit=False):
        selected = language_choices(codes, self._selected, self.with_auto)
        changed = selected != self._selected
        self._selected = selected
        self._updating = True
        self.setCurrentIndex(self.findData(selected[0]))
        for index in range(self.count()):
            code = self.itemData(index)
            item = self.model().item(index)
            item.setCheckable(True)
            item.setCheckState(Qt.Checked if code in selected else Qt.Unchecked)
            item.setEnabled(code in selected or code == AUTO or len(selected) < 3)
        self._updating = False
        self.ensurePolished()
        self.setFixedWidth(self.fontMetrics().horizontalAdvance(self.currentText()) + 24)
        self.view().setMinimumWidth(max(self.fontMetrics().horizontalAdvance(self.itemText(i))
                                       for i in range(self.count())) + 48)
        self.update()
        if changed and emit:
            self.selection_changed.emit(self.selected_codes())

    def _single_chosen(self, index):
        if not self._updating and index >= 0:
            self.set_selected([self.itemData(index)], emit=True)

    def _toggle(self, index):
        if not index.isValid():
            return
        code = self.itemData(index.row())
        selected = self.selected_codes()
        if code in selected:
            if len(selected) == 1:
                return
            selected.remove(code)
        elif code == AUTO:
            selected = [AUTO]
        else:
            selected = [value for value in selected if value != AUTO]
            if len(selected) == 3:
                return
            selected.append(code)
        self.set_selected(selected, emit=True)

    def eventFilter(self, watched, event):
        if watched is self.view().viewport() and event.type() == QEvent.MouseButtonRelease:
            if event.button() == Qt.LeftButton:
                self._toggle(self.view().indexAt(event.position().toPoint()))
                return True
        if watched is self.view() and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
                self._toggle(self.view().currentIndex())
                return True
        return super().eventFilter(watched, event)

    def retranslate(self):
        for index in range(self.count()):
            code = self.itemData(index)
            self.setItemText(index, tr("Auto-detect") if code == AUTO else tr(LANGS[code]))
        self.set_selected(self._selected)

    def paintEvent(self, event):
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        option.currentText = self.currentText()
        painter = QStylePainter(self)
        painter.drawComplexControl(QStyle.CC_ComboBox, option)
        painter.drawControl(QStyle.CE_ComboBoxLabel, option)
