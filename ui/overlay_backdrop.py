"""A painted, input-transparent surface behind the interactive overlay."""
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QEvent, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import QWidget

CLICK_THROUGH_BELOW = 30


class OverlayBackdrop(QWidget):
    def __init__(self, overlay):
        # An owned native window would be forced above the subtitle text on Windows.
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint |
                         Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.overlay = overlay
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_QuitOnClose, False)
        overlay.installEventFilter(self)
        overlay.destroyed.connect(self.deleteLater)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Hide, QEvent.Close):
            self.hide()
        elif event.type() in (QEvent.Show, QEvent.Move, QEvent.Resize,
                              QEvent.WindowStateChange, QEvent.WindowActivate,
                              QEvent.ZOrderChange):
            self.sync()
        return False

    def sync(self):
        overlay = self.overlay
        if (not overlay.isVisible() or overlay.isMinimized()
                or not 0 < overlay.settings.backdrop < CLICK_THROUGH_BELOW):
            self.hide()
            return
        self.setGeometry(overlay.geometry())
        self.show()
        if QGuiApplication.platformName() == "windows":
            user = ctypes.windll.user32
            user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
            user.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                         ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
            rect = wintypes.RECT()
            if user.GetWindowRect(int(overlay.winId()), ctypes.byref(rect)):
                # Place directly behind the text, without activation, in physical pixels.
                user.SetWindowPos(int(self.winId()), int(overlay.winId()), rect.left, rect.top,
                                  rect.right - rect.left, rect.bottom - rect.top, 0x0210)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(11, 11, 13, round(255 * self.overlay.settings.backdrop / 100)))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
