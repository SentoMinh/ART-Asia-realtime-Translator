"""Colours, icons and the style sheet."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

BG = "#0b0b0d"
PANEL = "#1a1a1e"
PANEL_HI = "#26262c"
LINE = "#34343c"
TEXT = "#ececf0"
DIM = "#9a9aa6"
ACCENT = "#5ab8ff"          # light blue
ACCENT_HOVER = "#82caff"
ON_ACCENT = "#06223a"       # text and icons on a light blue button (white would be hard to read)
ACCENT_OFF = "#1c3446"      # a disabled light blue button
ACCENT_OFF_TEXT = "#6f8ca3"
OK = "#3ddc84"
WARN = "#ffb454"
ERROR = "#ff5c6c"

STATUS_COLORS = {"ok": OK, "warn": WARN, "error": ERROR}
# one colour per speaker number; "You" uses ACCENT, so no speaker is light blue
SPEAKER_COLORS = ["#ffb454", "#6ee7a0", "#ff8fb3", "#c4a2ff", "#f5e663", "#ff9a76"]


def speaker_color(number: int) -> str:
    return SPEAKER_COLORS[(max(number, 1) - 1) % len(SPEAKER_COLORS)]


_SVG = {
    "play": '<path d="M8 5l11 7-11 7z" fill="currentColor"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="1" fill="currentColor"/>',
    "reload": '<path d="M20 7v5h-5M20 12a8 8 0 1 0-2.3 5.7"/>',
    "music": '<path d="M9 17V5l11-2v12M9 8l11-2"/><ellipse cx="6" cy="17" rx="3" ry="2.5"/>'
             '<ellipse cx="17" cy="15" rx="3" ry="2.5"/>',
    "mic": '<rect x="9" y="3" width="6" height="11" rx="3"/>'
           '<path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7"/>',
    "mic_off": '<rect x="9" y="3" width="6" height="11" rx="3"/>'
               '<path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7M4 3.5l16 17"/>',
    "speaker": '<path d="M4 9.5v5h3.5l4.5 4v-13l-4.5 4z"/>'
               '<path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11"/>',
    "speaker_off": '<path d="M4 9.5v5h3.5l4.5 4v-13l-4.5 4z"/><path d="M16 9.5l5 5M21 9.5l-5 5"/>',
    "wave": '<path d="M4 10v4M8 7v10M12 4v16M16 7v10M20 10v4"/>',
    "wave_off": '<path d="M4 11.5v1M8 11.5v1M12 11.5v1M16 11.5v1M20 11.5v1"/>',
    "pin": '<path d="M9 3.5h6l-1 6 3 3.5H7l3-3.5zM12 13v7.5"/>',
    "gear": '<circle cx="12" cy="12" r="2.8"/><circle cx="12" cy="12" r="6.4"/>'
            '<path d="M12 2.6v3M12 18.4v3M2.6 12h3M18.4 12h3M5.4 5.4l2.1 2.1M16.5 16.5l2.1 2.1'
            'M5.4 18.6l2.1-2.1M16.5 7.5l2.1-2.1"/>',
    "min": '<path d="M6 12h12"/>',
    "max": '<rect x="6.5" y="6.5" width="11" height="11" rx="1"/>',
    "close": '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
    "swap": '<path d="M6 8.5h12l-3-3M18 15.5H6l3 3"/>',
    "globe": '<circle cx="12" cy="12" r="8.5"/>'
             '<path d="M3.5 12h17M12 3.5c-3.2 2.6-3.2 14.4 0 17M12 3.5c3.2 2.6 3.2 14.4 0 17"/>',
    "down":'<path d="M7 10l5 5 5-5"/>',
    "dock": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 16L8 9M8 9h5M8 9v5"/>',
    "trash":'<path d="M5 7h14M10 7V4.5h4V7M7 7l1 12.5h8L17 7"/>',
}


def icon(name: str, color: str = TEXT, size: int = 18) -> QIcon:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
           f'stroke="{color}" stroke-width="1.7" stroke-linecap="round" '
           f'stroke-linejoin="round">{_SVG[name]}</svg>')
    scale = 3  # drawn larger than shown, so it stays sharp on scaled screens
    pixmap = QPixmap(QSize(size * scale, size * scale))
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter, QRectF(0, 0, size * scale, size * scale))
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    return QIcon(pixmap)


def style_sheet() -> str:
    return f"""
    * {{ color: {TEXT}; font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif; font-size: 13px; }}
    QToolTip {{ background: {PANEL}; color: {TEXT}; border: 1px solid {LINE}; padding: 4px 6px; }}
    QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 4px; }}
    QToolButton:hover {{ background: rgba(255,255,255,26); }}
    QToolButton#close:hover {{ background: {ERROR}; }}
    QToolButton:focus {{ border: 1px solid {ACCENT}; }}
    QLabel#dim {{ color: {DIM}; font-size: 12px; }}
    QComboBox {{ background: rgba(255,255,255,18); border: 1px solid transparent;
                 border-radius: 6px; padding: 3px 8px; min-height: 20px; }}
    QComboBox:hover, QComboBox:focus {{ border: 1px solid {ACCENT}; }}
    QComboBox::drop-down {{ border: none; width: 0px; }}
    QComboBox::down-arrow {{ image: none; width: 0px; }}
    QComboBox QAbstractItemView {{ background: {PANEL}; border: 1px solid {LINE};
                 selection-background-color: {ACCENT}; outline: none; }}
    QLineEdit {{ background: transparent; border: none; border-bottom: 1px solid {LINE};
                 padding: 5px 2px; selection-background-color: {ACCENT}; }}
    QLineEdit:focus {{ border-bottom: 1px solid {ACCENT}; }}
    QPushButton {{ background: {ACCENT}; color: {ON_ACCENT}; border: none; border-radius: 6px;
                   padding: 7px 14px; font-weight: 600; }}
    QPushButton:hover {{ background: {ACCENT_HOVER}; }}
    QPushButton:disabled {{ background: {ACCENT_OFF}; color: {ACCENT_OFF_TEXT}; }}
    QPushButton#send {{ border-top-right-radius: 0; border-bottom-right-radius: 0; }}
    QToolButton#sendLang {{ background: {ACCENT}; border: none; border-left: 1px solid rgba(0,0,0,70);
                            border-radius: 0; border-top-right-radius: 6px;
                            border-bottom-right-radius: 6px; padding: 6px 3px; }}
    QToolButton#sendLang:hover {{ background: {ACCENT_HOVER}; }}
    QToolButton#sendLang:focus {{ border: 1px solid white; }}
    QToolButton#sendLang::menu-indicator {{ image: none; }}
    QMenu {{ background: {PANEL}; border: 1px solid {LINE}; border-radius: 6px; padding: 4px; }}
    QMenu::item {{ padding: 6px 22px 6px 10px; border-radius: 4px; }}
    QMenu::item:selected {{ background: {PANEL_HI}; }}
    QMenu::item:checked {{ color: {ACCENT}; font-weight: 600; }}
    QMenu::indicator {{ width: 0; }}
    QPushButton#plain {{ background: {PANEL_HI}; color: {TEXT}; font-weight: 400; }}
    QPushButton#plain:hover {{ background: {LINE}; }}
    QFrame#inputBar {{ background: rgba(0,0,0,120); border: 1px solid {LINE}; border-radius: 9px; }}
    QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: rgba(255,255,255,50); border-radius: 2px; min-height: 24px; }}
    QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,90); }}
    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
        background: transparent; height: 0; }}
    QSlider::groove:horizontal {{ height: 4px; background: {LINE}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: {ACCENT}; width: 16px; margin: -6px 0; border-radius: 8px; }}
    QProgressBar {{ background: {LINE}; border: none; border-radius: 3px; max-height: 6px; }}
    QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
    QDialog#settings {{ background: #202024; }}
    QFrame#navPanel {{ background: transparent; border: none; border-right: 1px solid {LINE}; }}
    QListWidget#nav {{ background: transparent; border: none; outline: none; padding: 8px 6px; }}
    QListWidget#nav::item {{ padding: 9px 12px; border-radius: 6px; color: {DIM}; }}
    QListWidget#nav::item:selected {{ background: {PANEL_HI}; color: {ACCENT}; }}
    QFrame#card {{ background: #2b2b31; border-radius: 10px; }}
    QLabel#title {{ font-size: 14px; font-weight: 600; }}
    QLabel#heading {{ font-size: 17px; font-weight: 600; }}
    """
