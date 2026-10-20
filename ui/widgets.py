"""Small painted controls: the sound level line and the on/off switch."""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QAbstractButton, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from . import theme
from .i18n import tr


class DialogPanel(QFrame):
    """Present existing dialog contents inside the owning window."""

    def __init__(self, dialog, parent=None):
        super().__init__(parent)
        self.dialog = dialog
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        heading = QHBoxLayout()
        title = QLabel(dialog.windowTitle())
        title.setObjectName("title")
        title.setWordWrap(True)
        heading.addWidget(title, 1)
        close = QPushButton(tr("Close"))
        close.setObjectName("plain")
        close.clicked.connect(dialog.reject)
        heading.addWidget(close)
        layout.addLayout(heading)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        dialog.setParent(scroll, Qt.Widget)
        dialog.setAttribute(Qt.WA_DeleteOnClose, False)
        dialog.setMinimumSize(0, 0)
        scroll.setWidget(dialog)
        layout.addWidget(scroll, 1)


class LevelBar(QWidget):
    """A thin line that fills with the sound level (0.0 – 1.0)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._level = 0.0
        self._active = True
        self.setFixedSize(54, 12)

    def level(self) -> float:
        return self._level

    def set_level(self, level: float) -> None:
        level = min(max(float(level), 0.0), 1.0)
        # fall slowly so short sounds stay visible
        self._level = level if level > self._level else max(level, self._level * 0.8)
        self.update()

    def set_active(self, active: bool) -> None:
        self._active = active
        if not active:
            self._level = 0.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        track = QRectF(0, self.height() / 2 - 1.5, self.width(), 3)
        painter.setBrush(QColor(255, 255, 255, 46 if self._active else 20))
        painter.drawRoundedRect(track, 1.5, 1.5)
        if self._active and self._level > 0.01:
            fill = QRectF(track)
            fill.setWidth(track.width() * self._level)
            painter.setBrush(QColor(theme.OK if self._level < 0.85 else theme.WARN))
            painter.drawRoundedRect(fill, 1.5, 1.5)


class Switch(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)

    def sizeHint(self) -> QSize:
        return QSize(42, 24)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        body = QRectF(1, 2, 40, 20)
        painter.setBrush(QColor(theme.ACCENT if self.isChecked() else "#4a4a54"))
        painter.drawRoundedRect(body, 10, 10)
        x = body.right() - 18 if self.isChecked() else body.left() + 2
        painter.setBrush(QColor("white"))
        painter.drawEllipse(QRectF(x, body.top() + 2, 16, 16))
        if self.hasFocus():
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QColor(255, 255, 255, 150))
            painter.drawRoundedRect(body.adjusted(-0.5, -0.5, 0.5, 0.5), 10, 10)
