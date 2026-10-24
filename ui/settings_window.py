"""Settings window: a list of pages on the left, cards with rows on the right."""
from __future__ import annotations

import threading
import time
import uuid
from html import escape
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFormLayout, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QProgressBar,
                               QPushButton, QMessageBox, QScrollArea, QSlider, QStackedWidget, QVBoxLayout,
                               QWidget)

from engine import local_model
from engine import services      # the online services: names, default models, saved keys

from . import __version__, local_download, theme
from .backend import AUTO, LANGS, PICK_LANGS
from .config import BACKDROP_RANGE, FONT_RANGE, VAD_RANGE, Settings
from .i18n import tr
from .language_picker import LanguagePicker

try:
    from vrc.audio import input_devices
except ImportError:      # numpy missing: no microphone list, only the Windows default
    def input_devices() -> list[str]:
        return []
from .widgets import DialogPanel, Switch

LOCAL_MODEL = "Local Model (this PC)"
LOCAL_NOTE = "Choose a hearing or translation model to download and run on this PC. No API key is needed."
LOCAL_DOWNLOAD_NOTE = "Download: {size}. The model becomes active when the download finishes. You can close this window while it continues."
SERVICE_NOTES = {
    "openai": "Whisper hears, GPT translates. Paid per use.",
    "gemini": "Hears and translates. Google gives a small free daily allowance.",
    "qwen": "Qwen3-ASR knows Cantonese; its open version heard best in the benchmark. Paid per use.",
    "mimo": "Translates only. Paid per use, at low prices.",
    "openrouter": "One key for many models, Qwen and MiMo among them. Paid per use.",
    "custom": "Any OpenAI-compatible address, such as a server on your own PC.",
}


def fill_lang_combo(combo: QComboBox, with_auto: bool, optional: bool = False) -> None:
    if optional:
        combo.addItem("", "")
    if with_auto:
        combo.addItem("", AUTO)
    for code in PICK_LANGS:
        combo.addItem("", code)
    retranslate_lang_combo(combo)
    combo.currentIndexChanged.connect(lambda: fit_combo(combo))


def retranslate_lang_combo(combo: QComboBox) -> None:
    for index in range(combo.count()):
        code = combo.itemData(index)
        combo.setItemText(index, tr("None") if not code else tr("Auto-detect") if code == AUTO else tr(LANGS[code]))
    fit_combo(combo)


def fit_combo(combo: QComboBox) -> None:
    """Make the box as wide as the text it shows; the drop-down list fits its longest line."""
    combo.ensurePolished()   # the style sheet's font must be applied before measuring
    metrics = combo.fontMetrics()
    room = 22   # the style sheet's side padding (8 + 8), the border, and a little air
    combo.setFixedWidth(metrics.horizontalAdvance(combo.currentText()) + room)
    longest = max((metrics.horizontalAdvance(combo.itemText(i)) for i in range(combo.count())),
                  default=0)
    combo.view().setMinimumWidth(longest + room)


def select_data(combo: QComboBox, data) -> None:
    combo.blockSignals(True)
    combo.setCurrentIndex(max(combo.findData(data), 0))
    combo.blockSignals(False)
    fit_combo(combo)


PICTURE_FILE = Path(__file__).resolve().parent.parent / "assets" / "icon.png"   # the program icon
PICTURE_PX = 112


def program_picture(size: int, ratio: float = 1.0) -> QPixmap | None:
    """The program icon, smoothly scaled to `size` px (sharp on scaled screens); None if missing."""
    source = QPixmap(str(PICTURE_FILE))
    if source.isNull():
        return None
    pixels = max(round(size * ratio), 1)
    picture = source.scaled(pixels, pixels, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    picture.setDevicePixelRatio(ratio)
    return picture


class SettingsWindow(QDialog):
    changed = Signal()   # the shared Settings object was edited

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._panel = None
        self._service_health = getattr(getattr(parent, "backend", None), "service_health", None)
        if self._service_health:
            self._service_health.changed.connect(self.show_service_status)
        self.setObjectName("settings")
        self.setWindowTitle(tr("Settings"))
        self.resize(680, 470)
        self._switches: dict[str, Switch] = {}
        self._sliders: dict[str, tuple[QSlider, QLabel, str, int]] = {}

        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # the left column: the page list, and the program's picture big in its bottom-left corner
        # (the title bar can only show it at 16 px)
        side = QFrame()
        side.setObjectName("navPanel")
        side.setFixedWidth(150)
        column = QVBoxLayout(side)
        column.setContentsMargins(0, 0, 0, 12)
        column.setSpacing(0)
        column.addWidget(self.nav, 1)
        self.program_picture = QLabel()
        self.program_picture.setObjectName("programPicture")
        picture = program_picture(PICTURE_PX, self.devicePixelRatioF())
        if picture is not None:
            self.program_picture.setPixmap(picture)
            self.program_picture.setFixedSize(PICTURE_PX, PICTURE_PX)
            column.addWidget(self.program_picture, 0, Qt.AlignHCenter | Qt.AlignBottom)
        else:
            self.program_picture.hide()
        self.version = QLabel(f"v{__version__}")
        self.version.setObjectName("dim")
        self.version.setAlignment(Qt.AlignHCenter)
        self.version.setToolTip(f"VRChat Translator {__version__}")
        column.addSpacing(4)
        column.addWidget(self.version, 0, Qt.AlignHCenter | Qt.AlignBottom)
        self.pages = QStackedWidget()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(side)
        layout.addWidget(self.pages, 1)

        self.my_lang = LanguagePicker()
        self.their_lang = LanguagePicker(with_auto=True)
        self.translated_to = LanguagePicker()
        self.my_lang.selection_changed.connect(lambda values: self._set("my_languages", values))
        self.their_lang.selection_changed.connect(lambda values: self._set("their_languages", values))
        self.translated_to.selection_changed.connect(lambda values: self._set("translated_to", values))
        self.chatbox_mode = QComboBox()
        self.chatbox_mode.addItem(tr("Follow 'They speak'"), True)
        self.chatbox_mode.addItem(tr("Custom languages"), False)
        self.chatbox_mode.setAccessibleName(tr("Chatbox languages"))
        self.chatbox_languages = LanguagePicker()
        self.chatbox_languages.setAccessibleName(tr("Custom languages"))
        self.chatbox_languages.selection_changed.connect(
            lambda values: self._set("chatbox_custom_languages", values))
        self.chatbox_mode.currentIndexChanged.connect(self._chatbox_mode_changed)
        chatbox_control = QWidget()
        chatbox_layout = QVBoxLayout(chatbox_control)
        chatbox_layout.setContentsMargins(0, 0, 0, 0)
        chatbox_layout.addWidget(self.chatbox_mode)
        chatbox_layout.addWidget(self.chatbox_languages)

        self._page("Translation", [
            ("I speak", "Choose up to 3 languages you speak.", self.my_lang),
            ("They speak", "Choose up to 3 languages they speak, or Auto-detect.", self.their_lang),
            ("Translated to", "Choose up to 3 translation languages to show on the panel.", self.translated_to),
            ("Chatbox languages", "Send your voice and Auto typed messages in up to 3 languages. Auto-detect follows the last language heard, or English until then.", chatbox_control),
            ("Voice detector", "Only listens while someone talks. Turn it off if it cuts words or "
                               "misses quiet voices.", self._switch("vad_on")),
            ("Show the original text", "Shows what was heard above its translation.",
             self._switch("show_original")),
            ("Add my own words", "Include the original with typed translations. Microphone messages always include the original on its own line.",
             self._switch("chatbox_original")),
            ("Add Speaker words", "Send other players' translation and original words to your VRChat "
                                  "chatbox.", self._switch("chatbox_speaker")),
        ])
        # (no Chatbox page: "typing" dots keep the value saved in ui.json, on by default)
        self._page("Appearance", [
            ("Message text size", "Size of the text in the chat log.",
             self._slider("font_px", FONT_RANGE, "")),
            ("Background darkness", "Below 30%, empty space lets clicks through. Text and top controls stay clickable.",
             self._slider("backdrop", BACKDROP_RANGE, "%")),
            ("Always on top", "Keeps the window above the game. Needs VRChat in windowed or "
                              "borderless mode.", self._switch("always_on_top")),
            ("Hide the bars when the mouse is away", "Only the chat log stays; move the mouse over "
                                                    "the window to bring the buttons back.",
             self._switch("auto_hide_bars")),
        ])
        self.mic_device = QComboBox()
        self.mic_device.setMaximumWidth(270)
        self.mic_device.addItem(tr("Windows default"), "")
        names = input_devices()
        if settings.mic_device and settings.mic_device not in names:
            names.append(settings.mic_device)     # unplugged right now: keep the choice visible
        for name in names:
            self.mic_device.addItem(name, name)
        self.mic_device.currentIndexChanged.connect(
            lambda: self._set("mic_device", self.mic_device.currentData()))
        self.restore_detector = QPushButton(tr("Restore detector defaults"))
        self.restore_detector.setCursor(Qt.PointingHandCursor)
        self.restore_detector.clicked.connect(self._restore_detector)
        self._page("Sound", [
            ("Microphone", "The microphone the translator listens to. Pick the same one as in VRChat.",
             self.mic_device),
            ("Detector strictness: other players", "Higher ignores music and noise better but can miss "
                                                   "quiet voices. 70% is the tested default.",
             self._slider("vad_sensitivity", (round(VAD_RANGE[0] * 100), round(VAD_RANGE[1] * 100)),
                          "%", scale=100)),
            ("Detector strictness: my microphone", "Higher ignores keyboard clicks and room noise better "
                                                   "but can miss your quiet words. 50% is the default.",
             self._slider("mic_vad_sensitivity", (round(VAD_RANGE[0] * 100), round(VAD_RANGE[1] * 100)),
                          "%", scale=100)),
            ("Voice detector", "Higher strictness is not higher recognition accuracy. Restore detection on, "
                               "microphone 50% and other players 70%. Strictness changes apply after the current sentence.",
             self.restore_detector),
        ])
        self.hearing = self._service_combo("hearing", services.offered(services.HEARING))
        self.translating = self._service_combo("translating", services.offered(services.TRANSLATING))
        self._hearing_desc = QLabel()
        self._translating_desc = QLabel()
        self.model_pickers = {}
        self.connect_buttons = {}
        self._model_choices = {}
        hearing_control = self._model_control("hearing", self.hearing)
        translating_control = self._model_control("translating", self.translating)
        self._service_status: dict[str, QLabel] = {}
        self._domains_host = QWidget()
        self._domains_layout = QVBoxLayout(self._domains_host)
        self._domains_layout.setContentsMargins(0, 0, 0, 0)
        self._refresh_domains()
        self._page("Models", [
            ("Hearing", self._hearing_desc, hearing_control),
            ("Translating", self._translating_desc, translating_control),
        ], more=[(LOCAL_MODEL, [(LOCAL_MODEL, LOCAL_NOTE, self._local_row())]),
                 ("Services", self._domains_host)])
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(0)
        self.sync()
        self._model_timer = QTimer(self)
        self._model_timer.setInterval(500)
        self._model_timer.timeout.connect(self._update_model_labels)
        self._model_timer.start()

    def _active_hearing_model(self) -> str:
        parent = self.parent()
        backend = getattr(parent, "backend", None) if parent else None
        svc = self.settings.hearing
        title = tr(LOCAL_MODEL) if svc == "local" else tr(services.title(svc))
        if svc == "local":
            model = local_model.MODELS[local_model.selected()][0]
        else:
            model = services.setting(svc, "hear_model")
        model = model or title
        return f"{model} ({title})" if model != title else title

    def _active_translating_model(self) -> str:
        parent = self.parent()
        backend = getattr(parent, "backend", None) if parent else None
        svc = self.settings.translating
        title = tr(services.title(svc))
        configured = tuple(services.translate_models(svc))
        chains = (getattr(backend, "_translator", None),
                  getattr(getattr(backend, "speech_engine", None), "_translator", None))
        results = [result for chain in chains
                   if (result := getattr(chain, "last_result", None))
                   and result[1:3] == (svc, configured)]
        if results:
            name = max(results, key=lambda result: result[0])[3]
            used_service, separator, model = name.partition(":")
            if separator and used_service == svc:
                return f"{model} ({title})"
            return name
        current_model = getattr(backend, "current_translating_model", "")
        current_svc = getattr(backend, "current_translating_service", "")
        if current_model in configured and (not current_svc or current_svc == svc):
            model = current_model
        else:
            model = configured[0] if configured else services.setting(svc, "translate_model")
        model = model or title
        return f"{model} ({title})" if model != title else title

    def _update_model_labels(self) -> None:
        self._sync_model_controls()
        hear_model = escape(self._active_hearing_model())
        trans_model = escape(self._active_translating_model())
        hear_base = tr("Turns speech into text.")
        trans_base = tr("Turns text into the other language.")
        in_use = tr("Currently in use:")
        self._hearing_desc.setText(
            f"{hear_base}<br><span style='color: #5ab8ff;'>{in_use}</span> <b>{hear_model}</b>"
        )
        self._translating_desc.setText(
            f"{trans_base}<br><span style='color: #5ab8ff;'>{in_use}</span> <b>{trans_model}</b>"
        )

    def _model_control(self, role: str, domains: QComboBox) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.addWidget(domains, 1)
        connect = QPushButton(tr("Connect"))
        connect.setObjectName("plain")
        connect.setAccessibleName(f"{tr('Connect')} — {tr('Hearing' if role == 'hearing' else 'Translating')}")
        connect.clicked.connect(lambda: self._connect_domain(role))
        row.addWidget(connect)
        layout.addLayout(row)
        picker = QComboBox()
        picker.setMinimumWidth(190)
        picker.setMaximumWidth(300)
        picker.setAccessibleName(tr("Hearing model" if role == "hearing" else "Translating models"))
        picker.setEditable(True)
        picker.lineEdit().setPlaceholderText(tr("Pick a model…"))
        dropdown = picker.lineEdit().addAction(theme.icon("down"), QLineEdit.TrailingPosition)
        dropdown.setText(tr("Pick a model…"))
        dropdown.triggered.connect(picker.showPopup)
        picker.currentIndexChanged.connect(lambda: self._choose_model(role))
        picker.lineEdit().editingFinished.connect(lambda: self._choose_model(role))
        layout.addWidget(picker)
        self.model_pickers[role] = picker
        self.connect_buttons[role] = connect
        return box

    def _sync_model_controls(self) -> None:
        for role, picker in self.model_pickers.items():
            service = getattr(self.settings, role)
            field = "hear_model" if role == "hearing" else "translate_model"
            selected = services.setting(service, field)
            models = (tuple(m for m, info in local_model.MODELS.items() if info[1] == role)
                      if service == "local" else tuple(services.catalog(service)))
            signature = (service, selected, models)
            if self._model_choices.get(role) != signature:
                self._model_choices[role] = signature
                picker.blockSignals(True)
                picker.clear()
                for model in dict.fromkeys((selected, *models)):
                    if model:
                        picker.addItem(model, model)
                picker.setCurrentIndex(picker.findData(selected))
                picker.setEditText(selected)
                picker.blockSignals(False)
            button = self.connect_buttons[role]
            health = self._service_health.status(service) if self._service_health and service != "local" else None
            status = health[0] if health else ""
            label = ("Set up…" if service == "local" else "Connected" if status == "Online" else
                     "…" if status == "Checking connection…" else "Connect")
            button.setText(tr(label))
            button.setEnabled(status != "Checking connection…")
            button.setToolTip(tr(health[1] or health[0]) if health else tr("Connect"))
            button.setStyleSheet(f"color: {theme.OK};" if status == "Online" else "")

    def _connect_domain(self, role: str) -> None:
        service = getattr(self.settings, role)
        if service == "local":
            self.set_up_local(role)
        elif services.missing(service):
            self.set_up(service)
        else:
            if self._service_health is None:
                from .service_health import ServiceHealth
                self._service_health = ServiceHealth(self)
                self._service_health.changed.connect(self.show_service_status)
            self._service_health.check(service)
        self._sync_model_controls()

    def _choose_model(self, role: str) -> None:
        picker = self.model_pickers[role]
        model = picker.currentText().strip()
        if not model:
            return
        service = getattr(self.settings, role)
        field = "hear_model" if role == "hearing" else "translate_model"
        if model == services.setting(service, field):
            return
        if service == "local" and (model not in local_model.MODELS or local_model.MODELS[model][1] != role
                                   or local_model.missing(model)):
            self._model_choices.pop(role, None)
            self._sync_model_controls()
            self.set_up_local(role)
            return
        try:
            services.save(service, **{field: model})
        except OSError as error:
            QMessageBox.warning(self, tr("Could not save"), str(error))
            return
        self.changed.emit()
        self._update_model_labels()

    def sync(self) -> None:
        """Show the current values (also after a change made in the main window)."""
        self.my_lang.set_selected(self.settings.spoken_languages(True))
        self.their_lang.set_selected(self.settings.spoken_languages(False))
        self.translated_to.set_selected(self.settings.panel_languages())
        select_data(self.chatbox_mode, self.settings.chatbox_follow)
        self.chatbox_languages.set_selected(self.settings.chatbox_custom_languages)
        self.chatbox_languages.setVisible(not self.settings.chatbox_follow)
        self.mic_device.blockSignals(True)
        self.mic_device.setCurrentIndex(max(self.mic_device.findData(self.settings.mic_device), 0))
        self.mic_device.blockSignals(False)
        select_data(self.hearing, self.settings.hearing)
        select_data(self.translating, self.settings.translating)
        for name, switch in self._switches.items():
            switch.blockSignals(True)
            switch.setChecked(getattr(self.settings, name))
            switch.blockSignals(False)
        for name, (slider, value, unit, scale) in self._sliders.items():
            shown = round(getattr(self.settings, name) * scale)
            slider.blockSignals(True)
            slider.setValue(shown)
            slider.blockSignals(False)
            value.setText(f"{shown}{unit}")
        for service in self._service_status:
            self.show_service_status(service)
        self._update_model_labels()

    def _service_combo(self, setting: str, choices: tuple[str, ...]) -> QComboBox:
        combo = QComboBox()
        for service in choices:
            if service == "local":
                combo.addItem(tr(LOCAL_MODEL), "local")
            else:
                combo.addItem(tr(services.title(service)), service)
        combo.currentIndexChanged.connect(lambda: self._pick(setting, combo))
        combo.currentIndexChanged.connect(lambda: fit_combo(combo))
        fit_combo(combo)
        return combo

    def _pick(self, setting: str, combo: QComboBox) -> None:
        if combo.currentData() == "local" and local_model.missing(local_model.selected(setting)):
            # not on this PC yet: the choice stays as it was, and the Local Model's window offers
            # the download (the main window switches to it when everything has arrived)
            select_data(combo, getattr(self.settings, setting))
            self.set_up_local(role=setting)
            return
        new_svc = combo.currentData()
        self._set(setting, new_svc)
        parent = self.parent()
        backend = getattr(parent, "backend", None) if parent else None
        if backend:
            if setting == "translating":
                backend.current_translating_service = new_svc
                models = services.translate_models(new_svc)
                backend.current_translating_model = models[0] if models else services.setting(new_svc, "translate_model")
                if hasattr(backend, "setting_switched") and hasattr(backend.setting_switched, "emit"):
                    backend.setting_switched.emit("translating", new_svc)
            elif setting == "hearing":
                backend.current_hearing_service = new_svc
                backend.current_hearing_model = local_model.MODELS[local_model.selected()][0] if new_svc == "local" else services.setting(new_svc, "hear_model")
                if hasattr(backend, "setting_switched") and hasattr(backend.setting_switched, "emit"):
                    backend.setting_switched.emit("hearing", new_svc)
        self._update_model_labels()

    @staticmethod
    def _status_row(status: QLabel, set_up) -> QWidget:
        """A status text and a "Set up…" button."""
        status.setObjectName("dim")
        button = QPushButton(tr("Set up…"))
        button.setObjectName("plain")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(set_up)
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(status)
        row.addWidget(button)
        return box

    def _service_row(self, service: str) -> QWidget:
        """"Ready" / "Not set up" and a button that opens the service's own small window.
        The engines read the saved values on every request, so a change works at once."""
        self._service_status[service] = QLabel()
        box = self._status_row(self._service_status[service], lambda: self.set_up(service))
        for symbol, label, action in (("+", "Add domain", self.add_domain),
                                       ("−", "Remove domain", lambda: self.remove_domain(service))):
            button = QPushButton(symbol)
            button.setObjectName("plain")
            button.setFixedWidth(32)
            button.setAccessibleName(tr(label))
            button.setToolTip(tr(label))
            button.setEnabled(symbol != "−" or service != "custom")
            button.clicked.connect(action)
            box.layout().addWidget(button)
        self.show_service_status(service)
        return box

    def _refresh_domains(self) -> None:
        while self._domains_layout.count():
            old = self._domains_layout.takeAt(0).widget()
            old.hide()
            old.deleteLater()
        self._service_status.clear()
        rows = [(services.title(service), services.setting(service, "url") or SERVICE_NOTES["custom"],
                 self._service_row(service)) for service in services.offered()]
        self._domains_layout.addWidget(self._card(rows))
        for role, combo in (("hearing", self.hearing), ("translating", self.translating)):
            combo.blockSignals(True)
            combo.clear()
            for service in services.offered(services.HEARING):
                combo.addItem(tr(services.title(service)), service)
            select_data(combo, getattr(self.settings, role))
            combo.blockSignals(False)
            fit_combo(combo)

    def add_domain(self) -> None:
        service = "custom_" + uuid.uuid4().hex
        def saved():
            self._refresh_domains()
            if self._service_health:
                self._service_health.check(service)
            self.changed.emit()
        self._open_panel(ServiceDialog(service, self), saved)

    def _open_panel(self, dialog, accepted=None) -> None:
        if self._panel:
            self._panel.dialog.reject()
        previous = self.pages.currentWidget()
        panel = self._panel = DialogPanel(dialog, self.pages)
        self.pages.addWidget(panel)
        self.pages.setCurrentWidget(panel)
        self.nav.setEnabled(False)
        def finished(result):
            self.pages.setCurrentWidget(previous)
            self.pages.removeWidget(panel)
            self._panel = None
            self.nav.setEnabled(True)
            panel.deleteLater()
            if result == QDialog.Accepted and accepted:
                accepted()
        dialog.finished.connect(finished)
        dialog.show()
        dialog.setFocus()

    def done(self, result):
        if self._panel:
            self._panel.dialog.reject()
        super().done(result)

    def remove_domain(self, service: str) -> None:
        if service == "custom":
            return
        try:
            services.remove_domain(service)
        except OSError as error:
            QMessageBox.warning(self, tr("Could not save"), str(error))
            return
        for role in ("hearing", "translating"):
            if getattr(self.settings, role) == service:
                setattr(self.settings, role, "custom")
        self._refresh_domains()
        self._update_model_labels()
        self.changed.emit()

    def show_service_status(self, service: str) -> None:
        if service not in self._service_status:
            return
        label = self._service_status[service]
        health = self._service_health.status(service) if self._service_health else None
        label.setText(tr(health[0]) if health else tr("Ready") if services.ready(service) else tr("Not set up"))
        label.setToolTip(tr(health[1]) if health else "")
        color = theme.OK if health and health[0] == "Online" else theme.WARN if health else theme.DIM
        label.setStyleSheet(f"color: {color};")
        if hasattr(self, "model_pickers"):
            self._sync_model_controls()

    def set_up(self, service: str) -> None:
        def saved():
            self._refresh_domains()
            if self._service_health:
                self._service_health.check(service)
            self.show_service_status(service)
            self._update_model_labels()
            self.changed.emit()      # the status line may now have something else to say
        self._open_panel(ServiceDialog(service, self), saved)

    def _local_row(self) -> QWidget:
        """The Local Model is no service, but it is set up in the same place: "Ready", "Not
        downloaded" or how far the download is, and a button that opens its small window."""
        self._local_status = QLabel()
        box = self._status_row(self._local_status, lambda: self.set_up_local())
        download = local_download.shared()
        download.progress.connect(self.show_local_status)
        download.finished.connect(self.show_local_status)
        self.show_local_status()
        return box

    def show_local_status(self, *_) -> None:
        download = local_download.shared()
        if download.active:
            text = f"{100 * local_model.arrived(model=download.model) // local_model.size(download.model)}%"
        elif any(not local_model.missing(model) for model in local_model.MODELS):
            text = tr("Ready")
        else:
            text = tr("Not downloaded")
        self._local_status.setText(text)

    def set_up_local(self, role="hearing") -> None:
        dialog = LocalModelDialog(self, role=role)
        dialog.selected.connect(self._activate_local)
        dialog.removed.connect(lambda _: (self.show_local_status(), self.sync()))
        dialog.close_button.hide()
        self._open_panel(dialog)

    def _activate_local(self, model: str) -> None:
        role = local_model.MODELS[model][1]  # The setup dialog has saved the choice.
        self._set(role, "local")
        self.show_local_status()
        self.sync()

    def _chatbox_mode_changed(self) -> None:
        follow = self.chatbox_mode.currentData()
        self.chatbox_languages.setVisible(not follow)
        self._set("chatbox_follow", follow)

    def _restore_detector(self) -> None:
        defaults = Settings()
        for name in ("vad_on", "vad_sensitivity", "mic_vad_sensitivity"):
            setattr(self.settings, name, getattr(defaults, name))
        self.sync()
        self.changed.emit()

    def _set(self, name: str, value) -> None:
        setattr(self.settings, name, value)
        self.changed.emit()

    def _switch(self, name: str) -> Switch:
        switch = Switch()
        switch.toggled.connect(lambda on: self._set(name, on))
        self._switches[name] = switch
        return switch

    def _slider(self, name: str, limits: tuple[int, int], unit: str, scale: int = 1) -> QWidget:
        """`scale` 100 shows a 0.0 – 1.0 setting as a percentage."""
        slider = QSlider(Qt.Horizontal)
        slider.setRange(*limits)
        slider.setFixedWidth(170)
        value = QLabel()
        value.setFixedWidth(42)
        value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._sliders[name] = (slider, value, unit, scale)

        def moved(number: int) -> None:
            value.setText(f"{number}{unit}")
            self._set(name, number if scale == 1 else number / scale)
        slider.valueChanged.connect(moved)
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(slider)
        row.addWidget(value)
        return box

    def _page(self, name: str, rows: list[tuple[str, str | QLabel, QWidget]],
              more: list[tuple[str, list[tuple[str, str, QWidget]]]] = ()) -> None:
        """A page: its heading and one card of rows, then `more` cards, each under a small
        heading of its own. A page taller than the window scrolls."""
        self.nav.addItem(tr(name))
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(12)
        heading = QLabel(tr(name))
        heading.setObjectName("heading")
        outer.addWidget(heading)
        outer.addWidget(self._card(rows))
        for subheading, card_rows in more:
            label = QLabel(tr(subheading))
            label.setObjectName("title")
            outer.addSpacing(6)
            outer.addWidget(label)
            outer.addWidget(card_rows if isinstance(card_rows, QWidget) else self._card(card_rows))
        outer.addStretch(1)
        scroll = QScrollArea()
        scroll.setObjectName("page")
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea#page, QScrollArea#page > QWidget > QWidget "
                             "{ background: transparent; }")
        scroll.setWidget(page)
        self.pages.addWidget(scroll)

    @staticmethod
    def _card(rows: list[tuple[str, str | QLabel, QWidget]]) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        inner = QVBoxLayout(card)
        inner.setContentsMargins(18, 10, 18, 10)
        inner.setSpacing(4)
        for title, description, control in rows:
            row = QHBoxLayout()
            row.setContentsMargins(0, 6, 0, 6)
            text = QVBoxLayout()
            text.setSpacing(1)
            title_label = QLabel(tr(title))
            title_label.setObjectName("title")
            title_label.setWordWrap(True)
            if isinstance(description, QLabel):
                description_label = description
            else:
                description_label = QLabel(tr(description))
            description_label.setObjectName("dim")
            description_label.setWordWrap(True)
            text.addWidget(title_label)
            text.addWidget(description_label)
            row.addLayout(text, 1)
            row.addSpacing(16)
            row.addWidget(control, 0, Qt.AlignVCenter)
            control.setAccessibleName(tr(title))
            inner.addLayout(row)
        return card


class ServiceDialog(QDialog):
    """API setup and model discovery. An empty key field keeps the saved key."""

    def __init__(self, service: str, parent=None, http=None):
        super().__init__(parent)
        self.service = service
        self._http = http
        info = services.info(service)
        self.setObjectName("settings")
        self.setWindowTitle(tr(info.name))
        self.setMinimumWidth(460)
        saved = services.saved().get(service) or {}

        def field(name: str, default: str) -> QLineEdit:
            edit = QLineEdit(str(saved.get(name) or ""))
            edit.setPlaceholderText(default)
            return edit
        self.url = field("url", info.url or "https://…/v1")
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        if saved.get("key"):
            self.key.setPlaceholderText(tr("Saved. Leave empty to keep it."))
        else:
            self.key.setPlaceholderText(tr("Paste the key here"))
        self.hear_model = field("hear_model", info.hear_model or tr("e.g. whisper-1"))
        self.translate_model = field("translate_model", info.translate_model or tr("e.g. gpt-5.4-mini"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(10)
        note = QLabel(tr(SERVICE_NOTES.get(service, SERVICE_NOTES["custom"])))
        note.setObjectName("dim")
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        form.setSpacing(8)
        self.domain_name = field("name", tr("Custom domain"))
        if services.is_custom(service):
            if service != "custom" and service not in services.saved():
                names = {services.title(item) for item in services.offered()}
                number = 2
                while f"{tr('Custom domain')} {number}" in names:
                    number += 1
                self.domain_name.setText(f"{tr('Custom domain')} {number}")
            form.addRow(tr("Name"), self.domain_name)
        form.addRow(tr("Address"), self.url)
        form.addRow(tr("Key"), self.key)
        if services.is_custom(self.service):
            self.fetch_btn = QPushButton(tr("Fetch models"))
            self.fetch_btn.setObjectName("plain")
            self.fetch_btn.setCursor(Qt.PointingHandCursor)
            self.fetch_btn.clicked.connect(self.fetch_models)
            form.addRow("", self.fetch_btn)
        if not services.is_custom(self.service):
            if info.can_hear:
                form.addRow(tr("Hearing model"), self.hear_model)
            form.addRow(tr("Translating models"), self.translate_model)
        layout.addLayout(form)
        hint = QLabel(tr("Fetch models and save, then choose models under Hearing and Translating.")
                      if services.is_custom(self.service) else
                      tr("Empty fields use the defaults shown. Several translating models can be "
                         "listed with commas: when one is at its limit, the next answers."))
        hint.setObjectName("dim")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        if info.get_key:
            link = QLabel(f'<a href="{info.get_key}" style="color: {theme.ACCENT}">{tr("Get a key")}</a>')
            link.setOpenExternalLinks(True)
            layout.addWidget(link)
        self.result = QLabel()
        self.result.setObjectName("dim")
        self.result.setWordWrap(True)
        layout.addWidget(self.result)
        buttons = QHBoxLayout()
        test = QPushButton(tr("Test"))
        test.setObjectName("plain")
        test.clicked.connect(self.test)
        cancel = QPushButton(tr("Cancel"))
        cancel.setObjectName("plain")
        cancel.clicked.connect(self.reject)
        save = QPushButton(tr("Save"))
        save.setDefault(True)
        save.clicked.connect(self.save)
        if not services.is_custom(self.service):
            buttons.addWidget(test)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)
        self._fetching = False
        self._fetch_again = False
        self._fetched_models = None
        self._fetched_credentials = None
        self._auto_fetch = QTimer(self)
        self._auto_fetch.setSingleShot(True)
        self._auto_fetch.setInterval(500)
        self._auto_fetch.timeout.connect(self.fetch_models)
        self._fetch_poll = QTimer(self)
        self._fetch_poll.setInterval(80)
        self._fetch_poll.timeout.connect(self._poll_models)
        self.key.textChanged.connect(self._credentials_changed)
        self.url.textChanged.connect(self._credentials_changed)
        self.finished.connect(self._stop_fetch)
        # Auto-fetch models on open when the service already has credentials saved
        if services.is_custom(self.service) and services.ready(self.service):
            self._auto_fetch.start()

    def _credentials(self):
        return (self.service, self.url.text().strip(), self.key.text().strip() or services.setting(self.service, "key"))

    def _credentials_changed(self):
        self._auto_fetch.stop()
        self._fetch_again = False
        self._fetched_models = None
        self._fetched_credentials = None
        self.result.clear()
        if services.is_custom(self.service) and self.url.text().strip() and self.key.text().strip():
            self._auto_fetch.start()

    def _stop_fetch(self, *_):
        self._auto_fetch.stop()
        self._fetch_poll.stop()
        self._fetching = self._fetch_again = False
        if hasattr(self, "fetch_btn"):
            self.fetch_btn.setEnabled(True)

    def fetch_models(self) -> None:
        self._auto_fetch.stop()
        if self._fetching:
            self._fetch_again = True
            return
        self._fetching = True
        self._fetch_again = False
        self._fetch_credentials = self._credentials()
        service, url, key = self._fetch_credentials
        http = self._http
        self.result.setText(tr("Fetching models…"))
        if hasattr(self, "fetch_btn"):
            self.fetch_btn.setText(tr("Fetch models"))
            self.fetch_btn.setEnabled(False)
        # The daemon only owns a result dict and immutable request inputs.
        # Closing the dialog stops polling; no worker accesses Qt widgets.
        result_holder = {}
        def worker():
            try:
                result_holder["models"] = services.fetch_models(service, url=url, key=key, http=http)
            except Exception as error:
                result_holder["error"] = error
        self._fetch_result = result_holder
        self._fetch_thread = threading.Thread(target=worker, daemon=True)
        self._fetch_started = time.monotonic()
        self._fetch_thread.start()
        self._fetch_poll.start()

    def _poll_models(self):
        elapsed = time.monotonic() - self._fetch_started
        if self._fetch_thread.is_alive() and elapsed < 30:
            return
        self._fetch_poll.stop()
        self._fetching = False
        if hasattr(self, "fetch_btn"):
            self.fetch_btn.setEnabled(True)
        changed = self._fetch_credentials != self._credentials()
        retry = self._fetch_again or (changed and services.is_custom(self.service) and bool(self.key.text().strip()))
        self._fetch_again = False
        if changed:
            # A response for the old key must not populate the new key's list.
            if retry:
                self._auto_fetch.start()
            return
        error = self._fetch_result.get("error")
        if self._fetch_thread.is_alive() or (error and "timed out" in str(error).lower()):
            self.result.setText(f"✗ {tr('Timed out. Click Fetch models to try again.')}")
        elif error:
            message = str(error)
            key = self._fetch_credentials[2] or services.setting(self.service, "key")
            if key:
                message = message.replace(key, "***")
            self.result.setText(f"✗ {message} — {tr('Click Fetch models to try again')}")
        else:
            models = self._fetch_result.get("models", [])
            self._fetched_models = models
            self._fetched_credentials = self._fetch_credentials
            if models:
                self.result.setText(f"✓ {tr('Found {count} models').format(count=len(models))}")
            else:
                self.result.setText(f"{tr('No models found')} — {tr('Click Fetch models to try again')}")
        if hasattr(self, "fetch_btn"):
            self.fetch_btn.setText(tr("Try again" if error or not self._fetch_result.get("models") else "Fetch models"))
        if retry:
            self._auto_fetch.start()

    def test(self) -> None:
        """Asks the service with what is typed (or saved), without saving."""
        service, url, key, http = self.service, self.url.text(), self.key.text(), self._http
        was_visible = self.isVisible()
        base = tr("Testing…").rstrip(".…")
        self.result.setText(f"{base}…")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()

        result_holder: dict = {}

        def worker():
            try:
                result_holder["res"] = services.check(
                    service, url=url, key=key, http=http
                )
            except Exception as error:
                result_holder["res"] = (False, str(error))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        start_time = time.time()
        while thread.is_alive():
            if was_visible and not self.isVisible():
                break
            now = time.time()
            dot_count = (int((now - start_time) * 3) % 3) + 1
            dots = "." * dot_count
            self.result.setText(f"{base}{dots}")
            QApplication.processEvents()
            thread.join(timeout=0.08)

        QApplication.restoreOverrideCursor()
        ok, text = result_holder.get("res", (False, "error"))
        self.result.setText(("✓ " if ok else "✗ ") + text)
        if ok and services.is_custom(self.service):
            self.fetch_models()

    def save(self) -> None:
        values = ({"name": self.domain_name.text()} if services.is_custom(self.service) else
                  {"hear_model": self.hear_model.text(), "translate_model": self.translate_model.text()})
        values["url"] = self.url.text()
        if self.key.text().strip():
            values["key"] = self.key.text()
        try:
            models = self._fetched_models if self._fetched_credentials == self._credentials() else None
            services.save(self.service, models=models, **values)
        except OSError as error:
            self.result.setText(f"✗ {tr('Could not save')}: {error}")
            return
        self.accept()


class LocalModelDialog(QDialog):
    """Every local model has its own download, progress and activation controls."""
    selected = Signal(str)
    removed = Signal(str)

    def __init__(self, parent=None, download: local_download.LocalDownload | None = None, role="hearing"):
        super().__init__(parent)
        self._download = download or local_download.shared()
        self._stopping = False
        self._delete_pending = None
        self.rows = {}
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setObjectName("settings")
        self.setWindowTitle(tr(LOCAL_MODEL))
        self.setMinimumSize(620, 480)
        self.resize(720, 560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(10)
        note = QLabel(tr(LOCAL_NOTE))
        note.setWordWrap(True)
        layout.addWidget(note)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        listing = QVBoxLayout(content)
        listing.setContentsMargins(0, 0, 8, 0)
        listing.setSpacing(14)
        for model, (title, category, _, _) in local_model.MODELS.items():
            panel = QFrame()
            panel.setObjectName("card")
            row = QHBoxLayout(panel)
            details = QVBoxLayout()
            heading = QLabel(f"{tr('Hearing' if category == 'hearing' else 'Translating')} — {title}")
            heading.setWordWrap(True)
            details.addWidget(heading)
            model_note = QLabel(tr(local_model.DESCRIPTIONS[model]))
            model_note.setObjectName("dim")
            model_note.setWordWrap(True)
            details.addWidget(model_note)
            result = QLabel()
            result.setWordWrap(True)
            details.addWidget(result)
            bar = QProgressBar()
            bar.setRange(0, 1000)
            bar.setTextVisible(False)
            details.addWidget(bar)
            row.addLayout(details, 1)
            buttons = QVBoxLayout()
            action = QPushButton(tr("Download"))
            action.setAccessibleName(f"{tr('Download')} {title}")
            action.setToolTip(tr(LOCAL_DOWNLOAD_NOTE).format(size=local_model.gb(local_model.size(model))))
            action.clicked.connect(lambda checked=False, model=model: self.start_or_stop(model))
            use = QPushButton(tr("Use model"))
            use.setAccessibleName(f"{tr('Use model')} {title}")
            use.clicked.connect(lambda checked=False, model=model: self.use_model(model))
            buttons.addWidget(action)
            buttons.addWidget(use)
            delete = QPushButton(tr("Delete"))
            delete.setObjectName("plain")
            delete.setAccessibleName(f"{tr('Delete model')} {title}")
            delete.setToolTip(tr("Delete this model's downloaded files and unfinished download. Shared NVIDIA libraries are kept."))
            delete.clicked.connect(lambda checked=False, model=model: self.delete_model(model))
            cancel = QPushButton(tr("Cancel"))
            cancel.setObjectName("plain")
            cancel.clicked.connect(self.cancel_delete)
            buttons.addWidget(delete)
            buttons.addWidget(cancel)
            buttons.addStretch(1)
            row.addLayout(buttons)
            listing.addWidget(panel)
            self.rows[model] = dict(action=action, use=use, result=result, bar=bar, delete=delete, cancel=cancel)
        for model, (title, _) in local_model.REMOVED_MODELS.items():
            if not local_model.has_files(model):
                continue
            panel = QFrame()
            panel.setObjectName("card")
            row = QHBoxLayout(panel)
            result = QLabel(f"{title}\n{tr('Removed model — files still on this PC')}")
            result.setWordWrap(True)
            row.addWidget(result, 1)
            delete = QPushButton(tr("Delete"))
            delete.setAccessibleName(f"{tr('Delete model')} {title}")
            delete.clicked.connect(lambda checked=False, model=model: self.delete_model(model))
            cancel = QPushButton(tr("Cancel"))
            cancel.clicked.connect(self.cancel_delete)
            row.addWidget(delete)
            row.addWidget(cancel)
            listing.addWidget(panel)
            self.rows[model] = dict(delete=delete, cancel=cancel, result=result)
        listing.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        close = self.close_button = QPushButton(tr("Close"))
        close.setObjectName("plain")
        close.clicked.connect(self.accept)
        layout.addWidget(close, alignment=Qt.AlignRight)
        self._download.progress.connect(self.show_progress)
        self._download.finished.connect(self.show_state)
        self.show_state()
        initial = self.rows[local_model.selected(role)]
        (initial["use"] if initial["use"].isEnabled() else initial["action"]).setFocus()

    def show_state(self, problem: str = "") -> None:
        if not self._download.active:
            self._stopping = False
        for model, row in self.rows.items():
            pending = self._delete_pending == model
            row["delete"].setVisible(local_model.has_files(model))
            row["delete"].setEnabled(not self._download.active)
            row["delete"].setText(tr("Confirm delete") if pending else tr("Delete"))
            row["cancel"].setVisible(pending)
            if model in local_model.REMOVED_MODELS:
                row["result"].setText(f"{local_model.REMOVED_MODELS[model][0]}\n" + tr(
                    "Delete downloaded files? You can download available models again." if pending else
                    "Removed model — files still on this PC" if local_model.has_files(model) else "Model deleted"))
                continue
            active = self._download.active and self._download.model == model
            missing = local_model.missing(model)
            can_download = (local_model.installed(model)
                            and (model != "large-v3-turbo" or local_model.nvidia_card()))
            needs_download = not local_model.ready(model=model)
            row["action"].setText(tr("Stop") if active else tr("Download"))
            row["action"].setEnabled(not self._stopping if active else
                                     not self._download.active and can_download and needs_download)
            row["use"].setVisible(not missing)
            row["use"].setEnabled(not missing and not self._download.active)
            done, total = local_model.arrived(model=model), local_model.size(model)
            row["bar"].setVisible(active or (needs_download and done > 0))
            row["bar"].setValue(round(1000 * done / total) if total else 0)
            status = (tr("Ready") if not missing and not needs_download else
                      missing if not can_download else
                      tr("{done} of {size}").format(done=local_model.gb(done), size=local_model.gb(total)))
            row["result"].setText(status)
            if pending:
                row["result"].setText(tr("Delete downloaded files? You can download available models again."))
            if problem and problem != local_download.STOPPED and model == self._download.model:
                row["result"].setText("✗ " + problem)

    def show_progress(self, done: float, total: float) -> None:
        self.show_state()
        row = self.rows[self._download.model]
        row["bar"].setValue(round(1000 * done / total) if total else 0)
        row["result"].setText(tr("{done} of {size}").format(done=local_model.gb(done),
                                                          size=local_model.gb(total)))

    def start_or_stop(self, model: str) -> None:
        self._delete_pending = None
        if self._download.active:
            if self._download.model == model:
                self._stopping = True
                self._download.stop()
        else:
            self._download.start(model)
        self.show_state()

    def cancel_delete(self) -> None:
        self._delete_pending = None
        self.show_state()

    def delete_model(self, model: str) -> None:
        if self._download.active:
            return
        if self._delete_pending != model:
            self._delete_pending = model
            self.show_state()
            return
        self._delete_pending = None
        try:
            local_model.delete(model)
        except local_model.DownloadError as error:
            self.show_state()
            self.rows[model]["result"].setText(f"✗ {error}")
            return
        self.show_state()
        self.rows[model]["result"].setText(tr("Model deleted"))
        self.removed.emit(model)

    def use_model(self, model: str) -> None:
        if self._download.active or local_model.missing(model):
            self.show_state()
            return
        try:
            local_model.select(model)
        except OSError as error:
            self.rows[model]["result"].setText(f"✗ {tr('Could not save')}: {error}")
            return
        self.selected.emit(model)
        self.accept()
