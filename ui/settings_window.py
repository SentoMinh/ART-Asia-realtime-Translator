"""Settings window: a list of pages on the left, cards with rows on the right."""
from __future__ import annotations

import importlib.util
import threading
import time
from html import escape
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFormLayout, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton,
                               QScrollArea, QSlider, QStackedWidget, QVBoxLayout, QWidget)

from engine import services   # the online services: names, default models, saved keys

from . import __version__, theme
from .backend import AUTO, LANGS, PICK_LANGS
from .config import BACKDROP_RANGE, FONT_RANGE, VAD_RANGE, Settings
from .i18n import tr

try:
    from vrc.audio import input_devices
except ImportError:      # numpy missing: no microphone list, only the Windows default
    def input_devices() -> list[str]:
        return []
from .widgets import Switch

LOCAL_MODEL = "Local Model (this PC)"
SERVICE_NOTES = {
    "dev": "Ask the developer for a key. It is used to hear speech and to translate.",
    "openai": "Whisper hears, GPT translates. Paid per use.",
    "gemini": "Hears and translates. Google gives a small free daily allowance.",
    "qwen": "Qwen3-ASR knows Cantonese; its open version heard best in the benchmark. Paid per use.",
    "mimo": "Translates only. Paid per use, at low prices.",
    "openrouter": "One key for many models, Qwen and MiMo among them. Paid per use.",
    "custom": "Any OpenAI-compatible address, such as a server on your own PC.",
}


def local_model_installed() -> bool:
    """The download leaves the local model out (it needs 2 GB of GPU libraries)."""
    return importlib.util.find_spec("faster_whisper") is not None


def fill_lang_combo(combo: QComboBox, with_auto: bool) -> None:
    if with_auto:
        combo.addItem("", AUTO)
    for code in PICK_LANGS:
        combo.addItem("", code)
    retranslate_lang_combo(combo)
    combo.currentIndexChanged.connect(lambda: fit_combo(combo))


def retranslate_lang_combo(combo: QComboBox) -> None:
    for index in range(combo.count()):
        code = combo.itemData(index)
        combo.setItemText(index, tr("Auto-detect") if code == AUTO else tr(LANGS[code]))
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

        self.my_lang = QComboBox()
        fill_lang_combo(self.my_lang, with_auto=False)
        self.my_lang.currentIndexChanged.connect(lambda: self._set("my_lang", self.my_lang.currentData()))
        self.their_lang = QComboBox()
        fill_lang_combo(self.their_lang, with_auto=True)
        self.their_lang.currentIndexChanged.connect(
            lambda: self._set("their_lang", self.their_lang.currentData()))

        self._page("Translation", [
            ("I speak", "Your language. Subtitles are translated into it.", self.my_lang),
            ("They speak", "Your microphone is translated into this language. Auto-detect uses the "
                           "language heard last. Typed text uses the Send menu.", self.their_lang),
            ("Voice detector", "Only listens while someone talks. Turn it off if it cuts words or "
                               "misses quiet voices.", self._switch("vad_on")),
            ("Show the original text", "Shows what was heard above its translation.",
             self._switch("show_original")),
            ("Add my own words", "The chatbox shows the translation, then what you said.",
             self._switch("chatbox_original")),
            ("Add Speaker words", "Send other players' translation and original words to your VRChat "
                                  "chatbox.", self._switch("chatbox_speaker")),
        ])
        # (no Chatbox page: "typing" dots keep the value saved in ui.json, on by default)
        self._page("Appearance", [
            ("Message text size", "Size of the text in the chat log.",
             self._slider("font_px", FONT_RANGE, "")),
            ("Background darkness", "100% is a solid panel. 0% leaves only the text over the game.",
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
        ])
        # the Dev key only in the developer's and friends' copies (engine/services.py)
        self.hearing = self._service_combo("hearing", services.offered(services.HEARING))
        self.translating = self._service_combo("translating", services.offered(services.TRANSLATING))
        self._hearing_desc = QLabel()
        self._translating_desc = QLabel()
        self._service_status: dict[str, QLabel] = {}
        self._page("Models", [
            ("Hearing", self._hearing_desc, self.hearing),
            ("Translating", self._translating_desc, self.translating),
        ], more=[("Services", [(services.title(service), SERVICE_NOTES[service], self._service_row(service))
                               for service in services.offered()])])
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
            model = "Whisper"
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
            return name  # a local translation add-on answered
        current_model = getattr(backend, "current_translating_model", "")
        current_svc = getattr(backend, "current_translating_service", "")
        if current_model and (not current_svc or current_svc == svc):
            model = current_model
        else:
            model = configured[0] if configured else services.setting(svc, "translate_model")
        model = model or title
        return f"{model} ({title})" if model != title else title


    def _update_model_labels(self) -> None:
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


    def sync(self) -> None:
        """Show the current values (also after a change made in the main window)."""
        select_data(self.my_lang, self.settings.my_lang)
        select_data(self.their_lang, self.settings.their_lang)
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
                if local_model_installed() or self.settings.hearing == "local":
                    combo.addItem(tr(LOCAL_MODEL), "local")
            else:
                combo.addItem(tr(services.title(service)), service)
        combo.currentIndexChanged.connect(lambda: self._set(setting, combo.currentData()))
        combo.currentIndexChanged.connect(lambda: fit_combo(combo))
        fit_combo(combo)
        return combo

    def _service_row(self, service: str) -> QWidget:
        """"Ready" / "Not set up" and a button that opens the service's own small window.
        The engines read the saved values on every request, so a change works at once."""
        status = QLabel()
        status.setObjectName("dim")
        self._service_status[service] = status
        button = QPushButton(tr("Set up…"))
        button.setObjectName("plain")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(lambda: self.set_up(service))
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(status)
        row.addWidget(button)
        self.show_service_status(service)
        return box

    def show_service_status(self, service: str) -> None:
        self._service_status[service].setText(tr("Ready") if services.ready(service) else tr("Not set up"))

    def set_up(self, service: str) -> None:
        if ServiceDialog(service, self).exec():
            self.show_service_status(service)
            self._update_model_labels()
            self.changed.emit()      # the status line may now have something else to say

    def _set(self, name: str, value) -> None:
        setattr(self.settings, name, value)
        self._update_model_labels()
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

    def _page(self, name: str, rows: list[tuple[str, str, QWidget]],
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
            outer.addWidget(self._card(card_rows))
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
    """One service's address, key and models. Empty model fields mean the service's defaults;
    an empty key field keeps the saved key."""

    def __init__(self, service: str, parent=None, http=None):
        super().__init__(parent)
        self.service = service
        self._http = http
        info = services.SERVICES[service]
        self.setObjectName("settings")
        self.setWindowTitle(tr(info.name))
        self.setMinimumWidth(460)
        saved = services.saved().get(service) or {}
        code = service == "dev"

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
        note = QLabel(tr(SERVICE_NOTES[service]))
        note.setObjectName("dim")
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        form.setSpacing(8)
        if code:
            form.addRow(tr("Dev key"), self.key)
        else:
            form.addRow(tr("Address"), self.url)
            form.addRow(tr("Key"), self.key)
            if self.service == "custom":
                self.fetch_btn = QPushButton(tr("Fetch models"))
                self.fetch_btn.setObjectName("plain")
                self.fetch_btn.setCursor(Qt.PointingHandCursor)
                self.fetch_btn.clicked.connect(self.fetch_models)
                form.addRow("", self.fetch_btn)
            if info.can_hear:
                if self.service == "custom":
                    self.hear_picker = QComboBox()
                    self.hear_picker.addItem(tr("Pick a model…"), "")
                    self.hear_picker.currentIndexChanged.connect(self._pick_hear_model)
                    hear_row = QHBoxLayout()
                    hear_row.addWidget(self.hear_model, 1)
                    hear_row.addWidget(self.hear_picker, 0)
                    form.addRow(tr("Hearing model"), hear_row)
                else:
                    form.addRow(tr("Hearing model"), self.hear_model)
            if self.service == "custom":
                self.translate_picker = QComboBox()
                self.translate_picker.addItem(tr("Pick a model…"), "")
                self.translate_picker.currentIndexChanged.connect(self._pick_translate_model)
                trans_row = QHBoxLayout()
                trans_row.addWidget(self.translate_model, 1)
                trans_row.addWidget(self.translate_picker, 0)
                form.addRow(tr("Translating models"), trans_row)
            else:
                form.addRow(tr("Translating models"), self.translate_model)
        layout.addLayout(form)
        if not code:
            hint = QLabel(tr("Empty fields use the defaults shown. Several translating models can be "
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
        buttons.addWidget(test)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _pick_hear_model(self) -> None:
        m = self.hear_picker.currentData()
        if m:
            self.hear_model.setText(m)

    def _pick_translate_model(self) -> None:
        m = self.translate_picker.currentData()
        if m:
            self.translate_model.setText(m)

    def fetch_models(self) -> None:
        if getattr(self, "_fetching", False):
            return
        self._fetching = True
        # Read widgets on the UI thread. The worker may outlive a closed dialog.
        service, url, key, http = self.service, self.url.text(), self.key.text(), self._http
        was_visible = self.isVisible()
        base = tr("Fetching models…").rstrip(".…")
        self.result.setText(f"{base}…")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        if hasattr(self, "fetch_btn"):
            self.fetch_btn.setText(tr("Fetch models"))
            self.fetch_btn.setEnabled(False)
        QApplication.processEvents()

        result_holder: dict = {}

        def worker():
            try:
                result_holder["models"] = services.fetch_models(
                    service, url=url, key=key, http=http
                )
            except Exception as error:
                result_holder["error"] = error

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        start_time = time.monotonic()
        while thread.is_alive():
            if was_visible and not self.isVisible():
                break
            now = time.monotonic()
            if now - start_time >= 30:
                result_holder["error"] = TimeoutError("connection timed out")
                break
            dot_count = (int((now - start_time) * 3) % 3) + 1
            dots = "." * dot_count
            self.result.setText(f"{base}{dots}")
            QApplication.processEvents()
            thread.join(timeout=0.08)

        QApplication.restoreOverrideCursor()
        self._fetching = False
        if was_visible and not self.isVisible():
            if hasattr(self, "fetch_btn"):
                self.fetch_btn.setEnabled(True)
            return

        if "error" in result_holder:
            err = result_holder["error"]
            elapsed = int(time.monotonic() - start_time)
            if "timed out" in str(err).lower() or elapsed >= 30:
                self.result.setText(f"✗ {tr('Timed out after 30s. Click Fetch models to try again.')}")
            else:
                self.result.setText(f"✗ {err} — {tr('Click Fetch models to try again')}")
            if hasattr(self, "fetch_btn"):
                self.fetch_btn.setText(tr("Try again"))
                self.fetch_btn.setEnabled(True)
            return

        models = result_holder.get("models", [])
        if not models:
            self.result.setText(f"{tr('No models found')} — {tr('Click Fetch models to try again')}")
            if hasattr(self, "fetch_btn"):
                self.fetch_btn.setText(tr("Try again"))
                self.fetch_btn.setEnabled(True)
            return

        if hasattr(self, "fetch_btn"):
            self.fetch_btn.setText(tr("Fetch models"))
            self.fetch_btn.setEnabled(True)

        self._populate_pickers(models)
        self.result.setText(f"✓ {tr('Found {count} models').format(count=len(models))}")

    def _populate_pickers(self, models: list[str]) -> None:
        if hasattr(self, "hear_picker"):
            self.hear_picker.blockSignals(True)
            self.hear_picker.clear()
            self.hear_picker.addItem(tr("Pick a model…"), "")
            for m in models:
                self.hear_picker.addItem(m, m)
            self.hear_picker.blockSignals(False)
            fit_combo(self.hear_picker)
        if hasattr(self, "translate_picker"):
            self.translate_picker.blockSignals(True)
            self.translate_picker.clear()
            self.translate_picker.addItem(tr("Pick a model…"), "")
            for m in models:
                self.translate_picker.addItem(m, m)
            self.translate_picker.blockSignals(False)
            fit_combo(self.translate_picker)

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
        if ok and self.service == "custom":
            self.fetch_models()

    def save(self) -> None:
        values = {"hear_model": self.hear_model.text(), "translate_model": self.translate_model.text()}
        if self.service != "dev":
            values["url"] = self.url.text()
        if self.key.text().strip():
            values["key"] = self.key.text()
        try:
            services.save(self.service, **values)
        except OSError as error:
            self.result.setText(f"✗ {tr('Could not save')}: {error}")
            return
        self.accept()
