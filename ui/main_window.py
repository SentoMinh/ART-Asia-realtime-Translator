"""The main window: status and switches on top, the chat log, and the text box."""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QCursor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFrame, QGraphicsDropShadowEffect, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton,
                               QToolButton, QToolTip, QVBoxLayout, QWidget)

from engine import local_model

from . import __version__, config, i18n, local_download, theme
from .backend import AUTO, LANGS, PICK_LANGS, Backend, Status, Utterance
from .config import Settings
from .i18n import tr
from .log_view import SHORT, LogView
from .language_picker import LanguagePicker
from .overlay_backdrop import CLICK_THROUGH_BELOW, OverlayBackdrop
from .settings_window import SettingsWindow
from .widgets import DialogPanel, LevelBar
from vrc.audio import input_devices, output_devices
from vrc.chatbox import vrchat_window_origin

GRIP = 6          # px along every edge and corner that resize the window
RESIZE_GRACE = 0.4  # seconds auto-hide waits after a native resize or move ends
SHADOW_BELOW = 50  # backdrop % under which the letters get a dark shadow instead of a background
WM_NCHITTEST = 0x0084
WM_ENTERSIZEMOVE, WM_EXITSIZEMOVE = 0x0231, 0x0232
HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT = 10, 11, 12, 13, 14
HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 15, 16, 17
HT = {(-1, -1): HTTOPLEFT, (0, -1): HTTOP, (1, -1): HTTOPRIGHT,
      (-1, 0): HTLEFT, (1, 0): HTRIGHT,
      (-1, 1): HTBOTTOMLEFT, (0, 1): HTBOTTOM, (1, 1): HTBOTTOMRIGHT}
METER_WIDE, METER_TIGHT = 38, 16   # px width of the two level meters
GAP = 2            # px between toolbar controls
DELAY_BAND = 24    # px dead band before the latency readout appears or hides


class TitleBar(QWidget):
    """Draggable header, including meters and click buttons without menus."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._press_position = None
        self._press_window_position = None
        self._dragging = False
        self._manual_drag = False

    def enable_child_dragging(self):
        for child in self.findChildren(QWidget):
            if isinstance(child, (QLabel, LevelBar)) or (
                    isinstance(child, QToolButton) and child.menu() is None):
                child.installEventFilter(self)

    def _start_system_move(self):
        handle = self.window().windowHandle()
        return bool(handle and handle.startSystemMove())

    def _begin_drag(self, target):
        self._dragging = True
        if isinstance(target, QToolButton):
            target.setDown(False)  # dragging must not activate the button
        self._manual_drag = not self._start_system_move()

    def _mouse_event(self, target, event):
        button = isinstance(target, QToolButton)
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self._press_position = event.globalPosition().toPoint()
            self._press_window_position = self.window().pos()
            self._dragging = self._manual_drag = False
            if not button:
                self._begin_drag(target)
            return not button
        if event.type() == QEvent.MouseMove and self._press_position is not None:
            if not event.buttons() & Qt.LeftButton:
                return False
            delta = event.globalPosition().toPoint() - self._press_position
            if not self._dragging and delta.manhattanLength() >= QApplication.startDragDistance():
                self._begin_drag(target)
            if self._manual_drag:
                self.window().move(self._press_window_position + delta)
            return self._dragging
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            dragged = self._dragging
            self._press_position = None
            self._dragging = self._manual_drag = False
            if dragged and button:
                target.setDown(False)
            return dragged or not button
        if event.type() == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton and not button:
            self.window().toggle_maximized()
            return True
        return False

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.MouseButtonPress, QEvent.MouseMove,
                            QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick):
            if self._mouse_event(watched, event):
                return True
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event):
        if not self._mouse_event(self, event):
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._mouse_event(self, event):
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if not self._mouse_event(self, event):
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if not self._mouse_event(self, event):
            super().mouseDoubleClickEvent(event)


class MainWindow(QWidget):
    def __init__(self, backend: Backend, settings: Settings, save=config.save):
        super().__init__()
        self.backend = backend
        self.settings = settings.clean()
        self._save = save
        self._dialog: SettingsWindow | None = None
        self._notice = None
        self._tour = None
        self._music_dialog = None
        self._music_active = False
        self._music_level = 0.0
        self._music_glow_effect = None
        self._tips: list[tuple[QWidget, str]] = []     # (widget, English tooltip), for retranslating
        self._labels: list[tuple[QLabel, str]] = []
        self._status = Status("warn", "Starting…", "")
        self._resizing = False
        self._resize_until = 0.0
        i18n.set_lang(settings.ui_lang)
        self.setWindowTitle("VRChat Translator")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(*config.MIN_SIZE)

        root = QVBoxLayout(self)
        root.setContentsMargins(GRIP + 2, GRIP + 2, GRIP + 2, 18)
        root.setSpacing(6)
        self.bars = QFrame()
        self.bars.setObjectName("bars")
        bars = QVBoxLayout(self.bars)
        bars.setContentsMargins(4, 2, 2, 4)
        bars.setSpacing(4)
        self.log = LogView()
        bars.addWidget(self._build_title_bar())
        bars.addWidget(self._build_lang_row())
        root.addWidget(self.bars)
        root.addWidget(self.log, 1)
        root.addWidget(self._build_input_bar())

        self._declined_switches: dict[tuple[str, str], float] = {}
        self._switch_dialog = None
        backend.status_changed.connect(self.show_status)
        backend.mic_level.connect(self.mic_bar.set_level)
        backend.speaker_level.connect(self.speaker_bar.set_level)
        backend.utterance.connect(self.show_utterance)
        backend.setting_switched.connect(self._on_setting_switched)
        backend.switch_prompt_requested.connect(self._on_switch_requested)
        local_download.shared().finished.connect(self._local_model_arrived)

        self._hover = QTimer(self)
        self._hover.timeout.connect(self._check_hover)
        self._hover.start(250)

        self.setWindowFlag(Qt.WindowStaysOnTopHint, settings.always_on_top)
        self.resize(settings.w, settings.h)
        self._fit_header()   # the toolbar has no second row, so its width sets the minimum
        self.resize(max(settings.w, self.minimumWidth()), settings.h)
        self._place()
        self._retranslate()
        self._apply()
        backend.apply_settings(settings)
        self._refresh_send_target()
        self._backdrop = OverlayBackdrop(self)

    # ---- building -------------------------------------------------------

    def _button(self, name: str, tip: str, slot, object_name: str = "") -> QToolButton:
        button = QToolButton()
        button.setIcon(theme.icon(name))
        button.setIconSize(QSize(18, 18))
        button.setCursor(Qt.PointingHandCursor)
        if slot:
            button.clicked.connect(slot)
        if tip:
            self._tips.append((button, tip))
        if object_name:
            button.setObjectName(object_name)
        return button

    def _build_title_bar(self) -> QWidget:
        bar = TitleBar()
        self._header = QGridLayout(bar)
        self._header.setContentsMargins(4, 0, 0, 0)
        self._header.setSpacing(GAP)
        self._header_status = QHBoxLayout()
        self._header_status.setSpacing(4)
        self._capture_bar = QWidget()
        row = self._capture_controls = QHBoxLayout(self._capture_bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(GAP)
        self._title_actions = QWidget()
        self.title_buttons = QHBoxLayout(self._title_actions)
        self.title_buttons.setContentsMargins(0, 0, 0, 0)
        self.title_buttons.setSpacing(GAP)
        self.title_buttons.addStretch(1)
        self.dot = QLabel()
        self.dot.setFixedSize(8, 8)
        self.status = QLabel()
        self.status.setObjectName("dim")
        self.status.setFixedWidth(self.status.fontMetrics().horizontalAdvance("VRChat") + 4)
        self.music_button = self._button("music", "Music to microphone", self.open_music)
        self.music_button.setFixedSize(28, 28)
        self.music_button.hide()
        self.mic_button = self._button("mic", "", lambda: self._flip("mic_on"))
        self.mic_device_button = self._audio_picker("mic_device", "Microphone input")
        self.mic_bar = LevelBar()
        self.mic_bar.setFixedWidth(METER_WIDE)
        self.speaker_button = self._button("speaker", "", lambda: self._flip("subtitles_on"))
        self.speaker_device_button = self._audio_picker("speaker_device", "Subtitle audio source")
        self.speaker_bar = LevelBar()
        self.speaker_bar.setFixedWidth(METER_WIDE)
        self.vad_button = self._button("wave", "", lambda: self._flip("vad_on"))
        self.vad_button.hide()
        self.delay = QLabel()
        self.delay.setObjectName("dim")
        # Reserve the widest reading so a new time never shifts the toolbar.
        self._delay_allowance = self.delay.fontMetrics().horizontalAdvance("99.9 s")
        self.delay.setMinimumWidth(self._delay_allowance)
        self._tips.append((self.delay, "How long the last translation took"))
        self.delay.setVisible(False)   # only shown when the row has room for it
        # the globe: the language of the window itself
        self.ui_lang_button = self._button("globe", "Language of the window", None)
        self.ui_lang_button.setPopupMode(QToolButton.InstantPopup)
        self.ui_lang_button.setStyleSheet("QToolButton::menu-indicator { image: none; }")
        self.ui_lang_button.hide()
        menu = QMenu(self.ui_lang_button)
        group = QActionGroup(menu)
        self.ui_lang_actions: dict[str, QAction] = {}
        for code, name in i18n.UI_LANGS.items():
            action = menu.addAction(name)
            action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, code=code: self._ui_lang_picked(code))
            group.addAction(action)
            self.ui_lang_actions[code] = action
        self.ui_lang_button.setMenu(menu)
        self.pin_button = self._button("pin", "", lambda: self._flip("always_on_top"))
        self._header_status.addWidget(self.dot)
        self._header_status.addWidget(self.status)
        self.dock_button = self._button("dock", "Move to VRChat's top-left corner", self.move_to_vrchat)
        self.dock_button.hide()
        row.addWidget(self.dock_button)
        row.addWidget(self.music_button)
        row.addWidget(self.mic_device_button)
        row.addWidget(self.mic_button)
        row.addWidget(self.mic_bar)
        row.addSpacing(6)
        row.addWidget(self.speaker_device_button)
        row.addWidget(self.speaker_button)
        row.addWidget(self.speaker_bar)
        row.addWidget(self.vad_button)
        row.addStretch(1)
        row.addWidget(self.delay)
        row.addSpacing(4)
        self.title_buttons.addWidget(self.ui_lang_button)
        self.title_buttons.addWidget(self.pin_button)
        self.gear_button = self._button("gear", "Settings", self.open_settings)
        self.min_button = self._button("min", "Minimise", self.showMinimized)
        self.max_button = self._button("max", "Maximise", self.toggle_maximized)
        self.close_button = self._button("close", "Close", self.close, "close")
        self.title_buttons.addWidget(self.gear_button)
        self.title_buttons.addWidget(self.min_button)
        self.title_buttons.addWidget(self.max_button)
        self.title_buttons.addWidget(self.close_button)
        self._header.addLayout(self._header_status, 0, 0)
        self._header.addWidget(self._capture_bar, 0, 1)
        self._header.addWidget(self._title_actions, 0, 2)
        self._header.setColumnStretch(1, 1)
        self._delay_shown = False
        self._meter_width = METER_WIDE
        self._fitting = False
        bar.enable_child_dragging()
        return bar

    def _audio_picker(self, setting: str, tip: str) -> QToolButton:
        button = self._button("down", tip, None)
        button.setIconSize(QSize(16, 16))
        button.setFixedWidth(18)
        button.setPopupMode(QToolButton.InstantPopup)
        button.setStyleSheet("QToolButton { padding: 4px 0; } "
                            "QToolButton::menu-indicator { image: none; }")
        menu = QMenu(button)
        menu.aboutToShow.connect(lambda: self._fill_audio_menu(menu, setting))
        button.setMenu(menu)
        return button

    def _fill_audio_menu(self, menu: QMenu, setting: str) -> None:
        menu.clear()
        selected = getattr(self.settings, setting)
        microphone = setting == "mic_device"
        devices = input_devices() if microphone else output_devices()
        choices = [("", tr("Windows default") if microphone else "VRChat")]
        choices.extend((name, name.removesuffix(" [Loopback]")) for name in devices)
        if selected and selected not in devices:
            choices.append((selected, f"{selected} ({tr('Unavailable')})"))
        for value, label in choices:
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(value == selected)
            action.setData(value)
            action.setEnabled(not value or value in devices)
            action.triggered.connect(lambda _checked=False, value=value: self._audio_picked(setting, value))

    def _audio_picked(self, setting: str, device: str) -> None:
        setattr(self.settings, setting, device)
        self.settings_changed()

    def _build_lang_row(self) -> QWidget:
        box = TitleBar()
        row = QHBoxLayout(box)
        row.setContentsMargins(4, 0, 0, 0)
        row.setSpacing(6)
        self.my_lang = LanguagePicker()
        self.their_lang = LanguagePicker(with_auto=True)
        self.translated_to = LanguagePicker()
        for picker in (self.my_lang, self.their_lang, self.translated_to):
            picker.selection_changed.connect(self._lang_picked)
        self._tips.extend([
            (self.my_lang, "Choose up to 3 languages you speak."),
            (self.their_lang, "Choose up to 3 languages they speak, or Auto-detect."),
            (self.translated_to, "Choose up to 3 translation languages to show on the panel."),
        ])
        self.swap_button = self._button("swap", "Swap the two languages", self._swap)
        for text, widget in (("I speak", self.my_lang), ("", self.swap_button),
                             ("They speak", self.their_lang), ("Translated to", self.translated_to)):
            if text:
                column = QVBoxLayout()
                column.setSpacing(2)
                label = QLabel(tr(text))
                label.setObjectName("dim")
                self._labels.append((label, text))
                column.addWidget(label)
                column.addWidget(widget)
                row.addLayout(column)
            else:
                row.addWidget(widget, 0, Qt.AlignBottom)
        row.addStretch(1)
        self.more_button = self._button("down", "More actions", None)
        self.more_button.setPopupMode(QToolButton.InstantPopup)
        self.more_button.setStyleSheet("QToolButton::menu-indicator { image: none; }")
        self.more_menu = QMenu(self.more_button)
        self.more_menu.aboutToShow.connect(lambda: self._fill_more_menu(self.more_menu))
        self.more_button.setMenu(self.more_menu)
        row.addWidget(self.more_button)
        box.enable_child_dragging()
        return box

    def _fill_more_menu(self, menu: QMenu) -> None:
        menu.clear()

        def action(icon: str, text: str, slot):
            item = menu.addAction(theme.icon(icon), tr(text))
            item.triggered.connect(lambda _checked=False, slot=slot: slot())
            return item

        action("dock", "Move to VRChat", self.move_to_vrchat)
        action("music", "Music to microphone", self.open_music)
        vad = menu.addAction(theme.icon("wave" if self.settings.vad_on else "wave_off"),
                              tr("Voice detector"))
        vad.setCheckable(True)
        vad.setChecked(self.settings.vad_on)
        vad.triggered.connect(lambda: self._flip("vad_on"))

        languages = menu.addMenu(theme.icon("globe"), tr("Language of the window"))
        for code, name in i18n.UI_LANGS.items():
            item = languages.addAction(name)
            item.setCheckable(True)
            item.setChecked(code == i18n.lang())
            item.triggered.connect(lambda _checked=False, code=code: self._ui_lang_picked(code))

        vr = self._vr_button()
        if vr is not None:
            item = menu.addAction(theme.icon("vr"), tr("VR"))
            item.triggered.connect(vr.click)

        menu.addSeparator()
        action("trash", "Clear the chat log", self.log.clear)

    def _vr_button(self):
        for index in range(self.title_buttons.count()):
            widget = self.title_buttons.itemAt(index).widget()
            if isinstance(widget, QToolButton) and widget.text() == "VR":
                return widget
        return None

    def _build_input_bar(self) -> QWidget:
        self.input_bar = QFrame()
        self.input_bar.setObjectName("inputBar")
        row = QHBoxLayout(self.input_bar)
        row.setContentsMargins(12, 6, 6, 6)
        row.setSpacing(10)
        self.input = QLineEdit()
        self.input.returnPressed.connect(self.send_typed)
        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("send")
        self.send_button.setCursor(Qt.PointingHandCursor)
        self.send_button.setEnabled(False)
        self.send_button.clicked.connect(self.send_typed)
        self.input.textChanged.connect(lambda text: self.send_button.setEnabled(bool(text.strip())))
        # the arrow: which language typed text is translated into
        self.send_lang_button = QToolButton()
        self.send_lang_button.setObjectName("sendLang")
        self.send_lang_button.setIcon(theme.icon("down", theme.ON_ACCENT, 14))
        self.send_lang_button.setIconSize(QSize(14, 14))
        self.send_lang_button.setCursor(Qt.PointingHandCursor)
        self.send_lang_button.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self.send_lang_button)
        group = QActionGroup(menu)
        self.send_lang_actions: dict[str, QAction] = {}
        for code in [AUTO] + list(PICK_LANGS):
            action = menu.addAction("")
            action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, code=code: self._send_lang_picked(code))
            group.addAction(action)
            self.send_lang_actions[code] = action
        menu.aboutToShow.connect(self._refresh_send_target)
        self.send_lang_button.setMenu(menu)
        buttons = QHBoxLayout()
        buttons.setSpacing(0)
        buttons.addWidget(self.send_button)
        buttons.addWidget(self.send_lang_button)
        row.addWidget(self.input, 1)
        row.addLayout(buttons)
        return self.input_bar

    # ---- from the backend -----------------------------------------------

    def show_status(self, status: Status) -> None:
        if status == self._status and self.status.text():
            return      # the 2-second VRChat check repeats it; restyling the dot repaints the window
        self._status = status
        self._draw_status()

    def _draw_status(self) -> None:
        status = self._status
        color = theme.STATUS_COLORS.get(status.level, theme.WARN)
        self.dot.setStyleSheet(f"background: {color}; border-radius: 4px;")
        self.status.setText("VRChat")
        self.status.setAccessibleName(f"VRChat: {tr(status.text)}")
        self.status.setToolTip(i18n.tr_lines(status.detail))
        self.dot.setToolTip(i18n.tr_lines(status.detail))

    def show_utterance(self, utterance: Utterance) -> None:
        self.log.add_or_update(utterance)
        if utterance.source == "speaker" and utterance.final:
            self._refresh_send_target()   # on Auto, the target follows the language just heard
        if utterance.final and utterance.latency_ms is not None:
            self.delay.setText(f"{utterance.latency_ms / 1000:.1f} s")

    # ---- user actions ---------------------------------------------------

    def _on_music_state_changed(self, active: bool) -> None:
        self._music_active = active
        if not active:
            self._music_level = 0.0
            self.music_button.setGraphicsEffect(None)
            self._music_glow_effect = None
            self._music_icon_size = None
            self.music_button.setIcon(theme.icon("music", theme.TEXT))
            self.music_button.setIconSize(QSize(18, 18))
        else:
            self._update_music_glow(0.0)

    def _update_music_glow(self, peak: float) -> None:
        if not getattr(self, "_music_active", False):
            return
        prev = getattr(self, "_music_level", 0.0)
        level = peak if peak > prev else max(peak, prev * 0.8)
        self._music_level = level

        size = 18 + int(round(level * 4))
        if size != getattr(self, "_music_icon_size", None):   # called 20 times a second while playing
            self._music_icon_size = size
            self.music_button.setIcon(theme.icon("music", theme.OK, size))
            self.music_button.setIconSize(QSize(size, size))

        if self._music_glow_effect is None:
            self._music_glow_effect = QGraphicsDropShadowEffect(self.music_button)
            self._music_glow_effect.setOffset(0, 0)
            self.music_button.setGraphicsEffect(self._music_glow_effect)
        blur = 6 + int(round(level * 14))
        alpha = min(255, int(130 + round(level * 125)))
        glow_color = QColor(theme.OK)
        glow_color.setAlpha(alpha)
        self._music_glow_effect.setColor(glow_color)
        self._music_glow_effect.setBlurRadius(blur)

    def open_music(self) -> None:
        if self._music_dialog is None:
            from .music_dialog import MusicDialog
            self._music_dialog = MusicDialog(self.settings, self)
            self._music_dialog.state_changed.connect(self._on_music_state_changed)
            self._music_dialog.peak_changed.connect(self._update_music_glow)
            self._music_dialog.settings_changed.connect(self.settings_changed)
        self._music_dialog.refresh()
        self._music_dialog.show()
        self._music_dialog.raise_()
        self._music_dialog.activateWindow()
        if self._music_dialog._attachment is None and not self._music_dialog._setup_prompted:
            self._music_dialog.offer_setup()

    def send_typed(self) -> None:
        text = self.input.text().strip()
        if text:
            self.backend.send_text(text)
            self.input.clear()

    def toggle_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def open_settings(self) -> None:
        if self._dialog is None:
            self._dialog = SettingsWindow(self.settings, self)
            self._dialog.changed.connect(self.settings_changed)
        self._dialog.sync()
        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()

    def _local_model_arrived(self, problem: str) -> None:
        """Activate the downloaded model, including when its setup window was closed."""
        model = local_download.shared().model
        if not problem and not local_model.missing(model):
            self._activate_local(model)

    def _activate_local(self, model: str) -> None:
        role = local_model.MODELS[model][1]
        if local_model.selected(role) != model:
            local_model.select(model)
        setattr(self.settings, role, "local")
        self.settings_changed()

    def _on_setting_switched(self, setting: str, value: str) -> None:
        if hasattr(self.settings, setting):
            if getattr(self.settings, setting, None) != value:
                setattr(self.settings, setting, value)
                self.settings_changed()
        if self._dialog:
            self._dialog.sync()

    def _on_switch_requested(self, category: str, failed_service: str, reason: str = "") -> None:
        if getattr(self, "_switch_dialog", None) is not None and self._switch_dialog.isVisible():
            return
        now = time.time()
        last_declined = self._declined_switches.get((category, failed_service), 0)
        if now - last_declined < 60:
            return
        current_active = getattr(self.settings, category, "")
        if current_active != failed_service:
            return

        from .switch_dialog import SwitchModelDialog
        dialog = SwitchModelDialog(category, failed_service, self.settings, reason=reason, parent=self)
        self._switch_dialog = dialog
        dialog.switched.connect(self._handle_model_switched)
        dialog.declined.connect(lambda: self._declined_switches.update({(category, failed_service): time.time()}))
        dialog.open_local_download.connect(self._open_local_model_download)
        dialog.open_settings_page.connect(self._open_settings_models)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _handle_model_switched(self, category: str, service: str, model_name: str) -> None:
        if getattr(self.settings, category, None) != service:
            setattr(self.settings, category, service)
            self.settings_changed()
        if category == "translating":
            self.backend.current_translating_service = service
            if model_name:
                self.backend.current_translating_model = model_name
                self.backend.setting_switched.emit("translating_model", model_name)
            self.backend.setting_switched.emit("translating", service)
        elif category == "hearing":
            self.backend.current_hearing_service = service
            if model_name:
                self.backend.current_hearing_model = model_name
                self.backend.setting_switched.emit("hearing_model", model_name)
            self.backend.setting_switched.emit("hearing", service)
        if self._dialog:
            self._dialog.sync()

    def _open_local_model_download(self) -> None:
        self._open_settings_models()
        self._dialog.set_up_local()

    def _open_settings_models(self, page_name: str = "Models") -> None:
        self.open_settings()
        if self._dialog:
            for i in range(self._dialog.nav.count()):
                if self._dialog.nav.item(i).text() == tr("Models"):
                    self._dialog.nav.setCurrentRow(i)
                    break

    def _flip(self, name: str) -> None:
        setattr(self.settings, name, not getattr(self.settings, name))
        self.settings_changed()

    def _lang_picked(self) -> None:
        self.settings.my_languages = self.my_lang.selected_codes()
        self.settings.their_languages = self.their_lang.selected_codes()
        self.settings.translated_to = self.translated_to.selected_codes()
        self.settings_changed()

    def _send_lang_picked(self, code: str) -> None:
        self.settings.send_lang = code
        self.settings_changed()

    def _refresh_send_target(self) -> None:
        """The Send button names the language the next typed line goes into."""
        choice = self.settings.send_lang
        targets = self.backend.target_langs()
        short = ", ".join(SHORT.get(target, target) for target in targets)
        self.send_lang_actions.get(choice, self.send_lang_actions[AUTO]).setChecked(True)
        name = ", ".join(tr(LANGS.get(target, target)) for target in targets)
        if choice == AUTO:
            self.send_button.setText(f"{tr('Send')} · {tr('Auto')} {short}")
            tip = tr("Auto: follows chatbox languages (right now: {lang})").format(lang=name)
        else:
            self.send_button.setText(f"{tr('Send')} · {short}")
            tip = tr("Translates into {lang}").format(lang=name)
        self.send_button.setToolTip(tip)
        self.send_lang_button.setToolTip(tr("Pick the language your typed text is translated into"))
        self.send_lang_button.setAccessibleName(tip)

    def _ui_lang_picked(self, code: str) -> None:
        self.settings.ui_lang = code
        self.settings_changed()

    def _retranslate(self) -> None:
        """Put every fixed text of the window into the current language."""
        for widget, text in self._tips:
            widget.setToolTip(tr(text))
            widget.setAccessibleName(tr(text))
        for label, text in self._labels:
            label.setText(tr(text))
        self.my_lang.setAccessibleName(tr("I speak"))
        self.their_lang.setAccessibleName(tr("They speak"))
        self.translated_to.setAccessibleName(tr("Translated to"))
        for picker in (self.my_lang, self.their_lang, self.translated_to):
            picker.retranslate()
        self.input.setPlaceholderText(tr("Type a message — Enter translates and sends it"))
        self.input.setAccessibleName(tr("Message to translate and send"))
        for code, action in self.send_lang_actions.items():
            action.setText(tr("Auto — follow chatbox languages") if code == AUTO else tr(LANGS[code]))
        for code, action in self.ui_lang_actions.items():
            action.setChecked(code == i18n.lang())
        self._draw_status()
        self.log.refresh()
        if self._dialog:            # the settings window is rebuilt in the new language
            visible, page = self._dialog.isVisible(), self._dialog.nav.currentRow()
            self._dialog.close()
            self._dialog.deleteLater()
            self._dialog = None
            if visible:
                self.open_settings()
                self._dialog.nav.setCurrentRow(page)

    def _swap(self) -> None:
        if AUTO in self.settings.spoken_languages(False):
            return
        self.settings.my_languages, self.settings.their_languages = (
            self.settings.spoken_languages(False), self.settings.spoken_languages(True))
        self.settings_changed()

    def settings_changed(self) -> None:
        self.settings.clean()
        self._apply()
        if self._dialog:
            self._dialog.sync()
        self.backend.apply_settings(self.settings)
        self._refresh_send_target()
        self._save_settings()

    # ---- look -----------------------------------------------------------

    def _apply(self) -> None:
        s = self.settings
        if i18n.lang() != s.ui_lang:
            i18n.set_lang(s.ui_lang)
            self._retranslate()
        self._toggle_look(self.mic_button, "mic", s.mic_on, "My mic → chatbox")
        self._toggle_look(self.speaker_button, "speaker", s.subtitles_on, "Other players → subtitles")
        self._toggle_look(self.vad_button, "wave", s.vad_on, "Voice detector")
        self.mic_bar.set_active(s.mic_on)
        self.speaker_bar.set_active(s.subtitles_on)
        for button, label, value in (
                (self.mic_device_button, "Microphone input", s.mic_device or tr("Windows default")),
                (self.speaker_device_button, "Subtitle audio source", s.speaker_device or "VRChat")):
            tip = f"{tr(label)}: {value}"
            button.setToolTip(tip)
            button.setAccessibleName(tip)
        self.pin_button.setIcon(theme.icon("pin", theme.ACCENT if s.always_on_top else theme.DIM))
        tip = tr("Always on top: on" if s.always_on_top else "Always on top: off")
        self.pin_button.setToolTip(tip)
        self.pin_button.setAccessibleName(tip)
        self.my_lang.set_selected(s.spoken_languages(True))
        self.their_lang.set_selected(s.spoken_languages(False))
        self.translated_to.set_selected(s.panel_languages())
        self.swap_button.setEnabled(AUTO not in s.spoken_languages(False))
        # the background darkness is the only background there is: no boxes behind the rows or
        # the buttons, so at a low setting only the letters show, with a shadow to stay readable
        self.log.set_look(s.font_px, s.show_original, s.backdrop < SHADOW_BELOW)
        on_top = bool(self.windowFlags() & Qt.WindowStaysOnTopHint)
        if on_top != s.always_on_top:
            visible = self.isVisible()
            self.setWindowFlag(Qt.WindowStaysOnTopHint, s.always_on_top)
            if visible:
                self.show()   # changing the flag hides the window
        if not s.auto_hide_bars:
            self._show_bars(True)
        if hasattr(self, "_backdrop"):
            self._backdrop.sync()
        self.update()

    @staticmethod
    def _toggle_look(button: QToolButton, name: str, on: bool, what: str) -> None:
        button.setIcon(theme.icon(name if on else name + "_off", theme.TEXT if on else theme.ERROR))
        template = "{what}: on (click to turn off)" if on else "{what}: off (click to turn on)"
        tip = tr(template).format(what=tr(what))
        button.setToolTip(tip)
        button.setAccessibleName(tip)

    def bars_shown(self) -> bool:
        return not self.bars.isHidden()

    def begin_onboarding(self) -> None:
        """Start at the first screen this profile still needs."""
        if not self.settings.ui_lang_chosen:
            self.show_language_prompt()
        elif not self.settings.first_run_done:
            self.show_first_run()
        elif not self.settings.tour_done:
            self.show_tour()
        else:
            self.show_update_notice()

    def show_language_prompt(self) -> None:
        if self.settings.ui_lang_chosen or self._notice:
            return
        from .first_run_dialog import LanguageDialog
        dialog = LanguageDialog(self, settings=self.settings, save=self._save_settings)
        panel = DialogPanel(dialog, self)
        self._embed_notice(dialog, panel, self._after_language)

    def _after_language(self) -> None:
        # Closing the card without a choice keeps the current language.
        if not self.settings.ui_lang_chosen:
            self.settings.ui_lang_chosen = True
            self._save_settings()
        self._apply()
        QTimer.singleShot(0, self.begin_onboarding)

    def show_first_run(self) -> None:
        if self.settings.first_run_done:
            if not self.settings.tour_done:
                self.show_tour()
            return
        if self._notice:
            return
        from .first_run_dialog import FirstRunDialog
        dialog = FirstRunDialog(self, settings=self.settings, save=self._save_settings)
        panel = DialogPanel(dialog, self)
        self._embed_notice(dialog, panel, self._after_first_run)

    def _after_first_run(self) -> None:
        if not self.settings.first_run_done:
            self.settings.first_run_done = True
            self._save_settings()
        QTimer.singleShot(0, self.begin_onboarding)

    def _close_notice(self) -> None:
        panel = self._notice
        if panel is None:
            return
        self.layout().removeWidget(panel)
        panel.hide()
        panel.setParent(None)
        panel.deleteLater()
        self._notice = None
        self.log.show()
        self.input_bar.setVisible(self.bars_shown())

    def _embed_notice(self, dialog, panel: DialogPanel, after=None) -> None:
        panel.setParent(self)
        self._notice = panel
        self.log.hide()
        self.input_bar.hide()
        self.layout().insertWidget(1, panel, 1)
        self._show_bars(True)

        def finished(_=None):
            self._close_notice()
            if after is not None:
                after()

        dialog.finished.connect(finished)
        dialog.show()

    def _tour_steps(self) -> list:
        from .tutorial import TourStep
        return [
            TourStep(None, tr("Quick tour"),
                     tr("This short tour shows the main buttons. Use Next to continue or Skip to close it.")),
            TourStep(self.mic_device_button, tr("Microphone input"),
                     tr("Choose the microphone the translator listens to. Pick the same one you use in VRChat.")),
            TourStep(self.mic_button, tr("Your voice"),
                     tr("Turns your microphone on or off. When it is on, your speech is translated into the chatbox.")),
            TourStep(self.speaker_device_button, tr("Subtitle audio source"),
                     tr("Choose which app or device the translator listens to for other players' voices.")),
            TourStep(self.speaker_button, tr("Other players"),
                     tr("Turns other players' subtitles on or off.")),
            TourStep(self.my_lang, tr("I speak"), tr("Choose up to 3 languages you speak.")),
            TourStep(self.swap_button, tr("Swap languages"),
                     tr("Swaps the languages you speak and the languages they speak.")),
            TourStep(self.their_lang, tr("They speak"),
                     tr("Choose up to 3 languages they speak, or Auto-detect.")),
            TourStep(self.translated_to, tr("Translated to"),
                     tr("Choose up to 3 languages shown in the subtitles.")),
            TourStep(self.more_button, tr("More actions"),
                     tr("Opens a vertical list of tools: move to VRChat, music, voice detector, "
                        "window language, VR and clear chat.")),
            TourStep(self.input, tr("Type a message"),
                     tr("Type a message here. Press Enter to translate and send it.")),
            TourStep(self.send_button, tr("Send"),
                     tr("Sends your typed message. The arrow beside it chooses the language it is translated into.")),
            TourStep(self.send_lang_button, tr("Send language"),
                     tr("Pick the language your typed text is translated into.")),
            TourStep(self.pin_button, tr("Always on top"),
                     tr("Keeps the window above the game. Needs VRChat in windowed or borderless mode.")),
            TourStep(self.gear_button, tr("Settings"),
                     tr("Opens settings for models, sound, chatbox and appearance.")),
        ]

    def show_tour(self) -> None:
        if self.settings.tour_done or self._tour is not None or self._notice:
            return
        from .tutorial import TourOverlay
        self._show_bars(True)
        tour = TourOverlay(self, self._tour_steps())
        self._tour = tour
        tour.finished.connect(self._tour_finished)
        tour.start()

    def _tour_finished(self) -> None:
        self._tour = None
        self.settings.tour_done = True
        self._save_settings()
        self.show_update_notice()

    def show_update_notice(self) -> None:
        if self._notice or self.settings.last_update_notice == __version__:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("What's new in {version}").format(version=__version__))
        layout = QVBoxLayout(dialog)
        for text in (
            "First-time setup now asks for your language, recommends local models, "
            "and can save a named self-hosted service.",
            "The guided manual highlights each control, and highlighted buttons can be clicked directly.",
            "Toolbar utilities now live in the More-actions arrow, with Settings beside the pin.",
            "The music dialog warns when very loud music can affect translation.",
        ):
            label = QLabel("• " + tr(text))
            label.setWordWrap(True)
            layout.addWidget(label)
        layout.addStretch(1)
        panel = DialogPanel(dialog, self)
        self._embed_notice(dialog, panel)
        self.settings.last_update_notice = __version__
        self._save_settings()

    def _show_bars(self, visible: bool) -> None:
        if self.bars_shown() != visible:
            self.bars.setVisible(visible)
            self.input_bar.setVisible(visible and self._notice is None)
            self.update()

    def _check_hover(self) -> None:
        if not self.settings.auto_hide_bars:
            return
        # A native edge drag resizes before Qt sees the mouse press and may keep the
        # pointer on (or just past) the frame, so an idle cursor check would blank the
        # whole window mid-drag.
        busy = (self._notice is not None or self._tour is not None
                or QApplication.activePopupWidget() is not None or self.input.hasFocus()
                or self._resizing or time.monotonic() < self._resize_until
                or bool(QGuiApplication.mouseButtons()))
        self._show_bars(busy or self.frameGeometry().contains(QCursor.pos()))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        bars = self.bars_shown()
        alpha = round(255 * self.settings.backdrop / 100)
        if self.settings.backdrop < CLICK_THROUGH_BELOW:
            # Windows passes clicks through alpha-zero pixels, including to other processes.
            painter.setPen(Qt.NoPen)
            # Darkness is painted behind this surface; alpha 1 keeps controls interactive.
            painter.setBrush(QColor(11, 11, 13, 1))
            height = self.bars.geometry().bottom() + 1 if bars else GRIP
            painter.drawRect(QRectF(0, 0, self.width(), height))
            # Keep the invisible resize border grabbable on every side and corner too.
            painter.drawRect(QRectF(0, 0, GRIP, self.height()))
            painter.drawRect(QRectF(self.width() - GRIP, 0, GRIP, self.height()))
            painter.drawRect(QRectF(0, self.height() - GRIP, self.width(), GRIP))
            if self.input_bar.isVisible():
                painter.drawRoundedRect(QRectF(self.input_bar.geometry()), 9, 9)
            return
        if bars:
            alpha = max(alpha, 1)   # alpha 0 lets clicks fall through to the game
        painter.setBrush(QColor(11, 11, 13, alpha))
        painter.setPen(QPen(QColor(255, 255, 255, 40)) if bars or alpha else Qt.NoPen)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)

    # ---- window ---------------------------------------------------------

    def _fit_header(self) -> None:
        """Size the one-row toolbar from the current width.

        The meters narrow one pixel at a time as the window shrinks, so nothing
        jumps while an edge is dragged; the latency readout only appears when the
        row has room for it, with a dead band so it cannot blink at the boundary.
        """
        if self._fitting:
            return
        self._fitting = True
        try:
            available = self.width()
            for layout in (self.layout(), self.bars.layout()):
                margins = layout.contentsMargins()
                available -= margins.left() + margins.right()

            status = self._header_status.minimumSize().width()
            buttons = self.title_buttons.minimumSize().width()
            margins = self._header.contentsMargins()
            inset = margins.left() + margins.right()
            gap = self._header.horizontalSpacing()
            # The style sheet font may arrive after construction, so refresh the reserved width.
            allowance = self.delay.fontMetrics().horizontalAdvance("99.9 s")
            if allowance != self._delay_allowance:
                self._delay_allowance = allowance
                self.delay.setMinimumWidth(allowance)
            delay_cost = self._delay_allowance + self._capture_controls.spacing()
            # Width the capture row needs with no meters and no latency.
            base = self._capture_controls.minimumSize().width() \
                - self._meter_width * 2 \
                - (delay_cost if self._delay_shown else 0)
            fixed = status + base + buttons + 2 * gap + inset
            full = fixed + 2 * METER_WIDE + delay_cost

            shown = available >= full + (0 if self._delay_shown else DELAY_BAND)
            room = available - fixed
            meter = max(METER_TIGHT, min(METER_WIDE, room // 2))
            if shown != self._delay_shown:
                self._delay_shown = shown
                self.delay.setVisible(shown)
            if meter != self._meter_width:
                self._meter_width = meter
                self.mic_bar.setFixedWidth(meter)
                self.speaker_bar.setFixedWidth(meter)

            # One constant minimum: the window must not resize itself while it is dragged.
            bar = self._header.parentWidget()
            minimum_width = fixed + 2 * METER_TIGHT
            if bar.minimumWidth() != minimum_width:
                bar.setMinimumWidth(minimum_width)
            minimum = self.layout().minimumSize().expandedTo(QSize(*config.MIN_SIZE))
            if self.minimumSize() != minimum:
                self.setMinimumSize(minimum)
        finally:
            self._fitting = False

    def event(self, event):
        result = super().event(event)
        if event.type() == QEvent.LayoutRequest and hasattr(self, "_fitting") and not self._fitting:
            self._fit_header()
        return result

    def resizeEvent(self, event):
        # Keep auto-hide quiet while an edge is being dragged: hiding the bars would
        # reflow the whole window for a frame.
        self._resize_until = time.monotonic() + RESIZE_GRACE
        self._fit_header()
        super().resizeEvent(event)

    def move_to_vrchat(self) -> None:
        origin = vrchat_window_origin()
        if origin is None:
            QToolTip.showText(self.dock_button.mapToGlobal(self.dock_button.rect().bottomLeft()),
                             tr("VRChat window not found. Open or restore VRChat first."), self.dock_button)
            return
        if self.isMaximized():
            self.showNormal()
        user = ctypes.windll.user32
        user.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_int, wintypes.UINT]
        # Native coordinates keep placement correct across monitors with different DPI.
        if not user.SetWindowPos(int(self.winId()), None, *origin, 0, 0, 0x0015):
            QToolTip.showText(self.dock_button.mapToGlobal(self.dock_button.rect().bottomLeft()),
                             tr("Could not move the translator window."), self.dock_button)
            return
        self.settings.x, self.settings.y = self.x(), self.y()
        self._save_settings()

    def _place(self) -> None:
        s = self.settings
        if (s.x, s.y) != (-1, -1) and QGuiApplication.screenAt(
                self.rect().translated(s.x, s.y).center()):
            self.move(s.x, s.y)
            return
        area = QGuiApplication.primaryScreen().availableGeometry()
        self.move(area.right() - self.width() - 40, area.bottom() - self.height() - 60)

    def _save_settings(self) -> None:
        try:
            self._save(self.settings)
        except OSError:
            pass   # a read-only settings file must not break the window

    def closeEvent(self, event):
        if self._music_dialog is not None:
            self._music_dialog.shutdown()
        box = self.normalGeometry() if self.isMaximized() else self.geometry()
        self.settings.x, self.settings.y = box.x(), box.y()
        self.settings.w, self.settings.h = box.width(), box.height()
        self._save_settings()
        super().closeEvent(event)

    def nativeEvent(self, event_type, message):
        # the window has no frame, so Windows is told which edge the mouse is on
        if sys.platform == "win32" and event_type == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            self._note_size_move(msg.message)
            if msg.message == WM_NCHITTEST and not self.isMaximized():
                code = self._edge_code(msg)
                if code:
                    return True, code
        return super().nativeEvent(event_type, message)

    def _note_size_move(self, message: int) -> None:
        """Follow Windows' own drag loop, which Qt does not report as a mouse press."""
        if message == WM_ENTERSIZEMOVE:
            self._resizing = True
        elif message == WM_EXITSIZEMOVE:
            self._resizing = False
            self._resize_until = time.monotonic() + RESIZE_GRACE

    @staticmethod
    def _edge_code(msg) -> int:
        x = ctypes.c_short(msg.lParam & 0xFFFF).value
        y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
        rect = wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(msg.hWnd, ctypes.byref(rect))
        grip = max(GRIP * ctypes.windll.user32.GetDpiForWindow(msg.hWnd) // 96, GRIP)
        side = -1 if x < rect.left + grip else (1 if x >= rect.right - grip else 0)
        edge = -1 if y < rect.top + grip else (1 if y >= rect.bottom - grip else 0)
        return HT.get((side, edge), 0)
