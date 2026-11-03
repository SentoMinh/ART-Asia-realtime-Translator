"""The first-run manual: dim the window, circle one control and explain it."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEvent, QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QRegion
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .i18n import tr

CARD_WIDTH = 340
SMALL_TARGET = 40          # controls up to this size get a small circle
CIRCLE_MIN, CIRCLE_MAX = 24, 34
RECT_RADIUS = 8


@dataclass
class TourStep:
    target: QWidget | None
    title: str
    text: str


class TourOverlay(QWidget):
    """A transparent sheet over the main window with one bright target.

    The sheet eats mouse input on purpose: the note and its buttons are the
    only controls during the manual, so a click cannot open a menu or a dialog
    behind the explanation.
    """

    finished = Signal()

    def __init__(self, parent: QWidget, steps: list[TourStep]):
        super().__init__(parent)
        self.setObjectName("tourOverlay")
        self.setAttribute(Qt.WA_NoMousePropagation, True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.steps = list(steps)
        self.index = 0
        self._done = False

        self.card = QFrame(self)
        self.card.setObjectName("tourCard")
        self.card.setAttribute(Qt.WA_StyledBackground, True)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(8)

        self.step_label = QLabel()
        self.step_label.setObjectName("tourStep")
        self.title_label = QLabel()
        self.title_label.setObjectName("tourTitle")
        self.title_label.setWordWrap(True)
        self.body_label = QLabel()
        self.body_label.setObjectName("tourBody")
        self.body_label.setWordWrap(True)
        card_layout.addWidget(self.step_label)
        card_layout.addWidget(self.title_label)
        card_layout.addWidget(self.body_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.skip_button = QPushButton(tr("Skip"))
        self.skip_button.setObjectName("plain")
        self.skip_button.setCursor(Qt.PointingHandCursor)
        self.next_button = QPushButton()
        self.next_button.setCursor(Qt.PointingHandCursor)
        buttons.addWidget(self.skip_button)
        buttons.addStretch(1)
        buttons.addWidget(self.next_button)
        card_layout.addLayout(buttons)
        self.skip_button.clicked.connect(self.finish)
        self.next_button.clicked.connect(self.advance)

        self.setGeometry(parent.rect())
        self._show_step()
        parent.installEventFilter(self)

    def start(self) -> None:
        self.setGeometry(self.parentWidget().rect())
        self._show_step()
        self.show()
        self.raise_()
        self.setFocus()

    def _show_step(self) -> None:
        if not self.steps:
            self.finish()
            return
        step = self.steps[self.index]
        self.step_label.setText(tr("Step {n} of {total}").format(n=self.index + 1, total=len(self.steps)))
        self.title_label.setText(step.title)
        self.body_label.setText(step.text)
        self.next_button.setText(tr("Next →") if self.index + 1 < len(self.steps) else tr("Done"))
        self.card.setFixedWidth(min(CARD_WIDTH, max(240, self.width() - 24)))
        self.card.adjustSize()
        self._place_card()
        self._update_mask()
        self.update()

    def _target_rect(self) -> QRectF | None:
        step = self.steps[self.index] if self.steps else None
        target = step.target if step else None
        if target is None or not target.isVisible():
            return None
        origin = target.mapTo(self.parentWidget(), QPoint(0, 0))
        return QRectF(origin.x(), origin.y(), target.width(), target.height())

    def _hole(self) -> tuple[QRectF, bool] | None:
        """The bright area and whether its outline is a circle."""
        rect = self._target_rect()
        if rect is None:
            return None
        if max(rect.width(), rect.height()) <= SMALL_TARGET:
            diameter = min(CIRCLE_MAX, max(CIRCLE_MIN, max(rect.width(), rect.height()) + 2))
            center = rect.center()
            return QRectF(center.x() - diameter / 2, center.y() - diameter / 2,
                          diameter, diameter), True
        return rect.adjusted(-8, -7, 8, 7), False

    def _hole_rect(self) -> QRectF | None:
        spot = self._hole()
        return spot[0] if spot is not None else None

    def _update_mask(self) -> None:
        """Let clicks reach the highlighted control through the dimmed sheet."""
        region = QRegion(self.rect())
        spot = self._hole()
        if spot is not None:
            hole, circle = spot
            rect = hole.toAlignedRect()
            region = region.subtracted(QRegion(rect, QRegion.Ellipse) if circle else QRegion(rect))
        self.setMask(region)

    def _place_card(self) -> None:
        spot = self._hole()
        width, height = self.width(), self.height()
        card = self.card
        if spot is None:
            x = (width - card.width()) // 2
            y = (height - card.height()) // 2
        else:
            hole = spot[0]
            if hole.center().y() < height / 2:
                y = int(hole.bottom()) + 14
            else:
                y = int(hole.top()) - card.height() - 14
            if y + card.height() > height - 10 or y < 10:
                y = int(hole.bottom()) + 14 if y < 10 else int(hole.top()) - card.height() - 14
            x = int(hole.center().x()) - card.width() // 2
        x = max(10, min(x, width - card.width() - 10))
        y = max(10, min(y, height - card.height() - 10))
        card.move(x, y)

    def advance(self) -> None:
        if self.index + 1 < len(self.steps):
            self.index += 1
            self._show_step()
        else:
            self.finish()

    def finish(self) -> None:
        if self._done:
            return
        self._done = True
        parent = self.parentWidget()
        parent.removeEventFilter(self)
        self.hide()
        self.finished.emit()
        self.deleteLater()

    def eventFilter(self, watched, event):
        if watched is self.parentWidget() and event.type() in (QEvent.Resize, QEvent.Show, QEvent.Move):
            self.setGeometry(self.parentWidget().rect())
            self._place_card()
            self._update_mask()
            self.update()
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.finish()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Right, Qt.Key_Space):
            self.advance()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        spot = self._hole()
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        if spot is not None:
            hole, circle = spot
            if circle:
                path.addEllipse(hole)
            else:
                path.addRoundedRect(hole, RECT_RADIUS, RECT_RADIUS)
        path.setFillRule(Qt.OddEvenFill)
        painter.fillPath(path, QColor(5, 5, 8, 185))
