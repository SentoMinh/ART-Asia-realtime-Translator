"""Initial setup dialog shown only on the first run of the application.

Lets the user choose between online services (lightweight default) or local models,
and optionally queue local models or install the music mixer.
"""
from __future__ import annotations

import logging
import sys
import threading
import uuid
from typing import Callable
from urllib.parse import urlsplit

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from engine import local_model, services
from vrc import driver_setup

from . import local_download, i18n, theme
from .config import Settings
from .i18n import tr

log = logging.getLogger("ui.first_run")


class LanguageDialog(QDialog):
    """The very first screen: ask which language the app and the manual use."""

    ORDER = ("zh", "vi", "en")

    def __init__(self, parent=None, settings: Settings | None = None, save: Callable[[], None] | None = None):
        super().__init__(parent)
        self.settings = settings or Settings()
        self.save_settings = save
        self.setObjectName("settings")
        self.setWindowTitle(tr("Choose your language"))
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        heading = QLabel(tr("Welcome to VRChat Translator"))
        heading.setObjectName("heading")
        layout.addWidget(heading)
        subtitle = QLabel(tr("Pick the language for the app and the user manual. You can change it later with the globe button."))
        subtitle.setObjectName("dim")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        self.buttons: dict[str, QPushButton] = {}
        for code in self.ORDER:
            button = QPushButton(i18n.UI_LANGS[code])
            button.setObjectName("languageChoice")
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(44)
            button.clicked.connect(lambda _checked=False, code=code: self.choose(code))
            layout.addWidget(button)
            self.buttons[code] = button

    def choose(self, code: str) -> None:
        if code not in i18n.UI_LANGS:
            code = "en"
        self.settings.ui_lang = code
        self.settings.ui_lang_chosen = True
        if self.save_settings:
            self.save_settings()
        self.accept()


def is_windows_11() -> bool:
    if sys.platform != "win32":
        return False
    try:
        return sys.getwindowsversion().build >= 22000
    except (AttributeError, OSError):
        return False


class ServiceNameDialog(QDialog):
    """Ask for the name shown in Settings -> Services/API."""

    def __init__(self, parent, default_name: str):
        super().__init__(parent)
        self.setObjectName("settings")
        self.setWindowTitle(tr("Save service"))
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        title = QLabel(tr("Save service"))
        title.setObjectName("title")
        layout.addWidget(title)
        note = QLabel(tr("Name this service"))
        note.setObjectName("dim")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.name_edit = QLineEdit(default_name)
        self.name_edit.setAccessibleName(tr("Name"))
        self.name_edit.selectAll()
        layout.addWidget(self.name_edit)
        buttons = QHBoxLayout()
        self.cancel_button = QPushButton(tr("Cancel"))
        self.cancel_button.setObjectName("plain")
        self.cancel_button.clicked.connect(self.reject)
        self.save_button = QPushButton(tr("Save"))
        self.save_button.clicked.connect(self.accept)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch(1)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)
        self.name_edit.returnPressed.connect(self.accept)


class FirstRunDialog(QDialog):
    models_fetched = Signal(bool, object, str)

    def __init__(self, parent=None, settings: Settings | None = None, save: Callable[[], None] | None = None):
        super().__init__(parent)
        self.settings = settings or Settings()
        self.save_settings = save
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setObjectName("settings")
        self.setWindowTitle(tr("Welcome to VRChat Translator"))
        self.setMinimumWidth(360)
        self.resize(480, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Title & Subtitle
        title = QLabel(tr("Initial Setup"))
        title.setObjectName("title")
        layout.addWidget(title)

        subtitle = QLabel(tr("Choose how VRChat Translator runs on your computer. You can change these anytime in Settings."))
        subtitle.setObjectName("dim")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # Mode Selection Card
        mode_card = QFrame()
        mode_card.setObjectName("card")
        mode_layout = QVBoxLayout(mode_card)
        mode_layout.setSpacing(8)

        self.mode_group = QButtonGroup(self)
        self.online_radio = QRadioButton(tr("Self-hosted"))
        self.local_radio = QRadioButton(tr("Local AI models"))
        self.mode_group.addButton(self.online_radio)
        self.mode_group.addButton(self.local_radio)
        self.local_radio.setChecked(True)

        for radio, description in (
                (self.online_radio, "Fast, lightweight, ready immediately."),
                (self.local_radio, "Recommended · offline privacy, runs on your PC.")):
            mode_layout.addWidget(radio)
            note = QLabel(tr(description))
            note.setObjectName("dim")
            note.setWordWrap(True)
            note.setContentsMargins(24, 0, 0, 0)
            if radio is self.local_radio:
                self.local_note = note
            mode_layout.addWidget(note)
        layout.addWidget(mode_card)

        # Optional Local Models Download Card
        self.models_card = models_card = QFrame()
        models_card.setObjectName("card")
        models_layout = QVBoxLayout(models_card)
        models_layout.setSpacing(8)

        self.download_check = QCheckBox(tr("Download AI models"))
        self.download_check.setChecked(True)
        models_layout.addWidget(self.download_check)

        self.models_picker = QWidget()
        picker_layout = QVBoxLayout(self.models_picker)
        picker_layout.setContentsMargins(18, 4, 0, 4)
        picker_layout.setSpacing(8)

        # Hearing model
        hear_box = QHBoxLayout()
        hear_lbl = QLabel(tr("Hearing:"))
        self.hear_combo = QComboBox()
        self.hear_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.hear_combo.setMinimumContentsLength(12)
        self.hear_combo.setMinimumWidth(140)
        for m in ("whisper-turbo-vulkan", "large-v3-turbo", "sensevoice", "phowhisper-small"):
            if m in local_model.MODELS:
                name, _, _, _ = local_model.MODELS[m]
                sz = local_model.gb(local_model.size(m))
                label = f"{tr(name)} ({sz})"
                if m == "large-v3-turbo":
                    label += " · " + tr("Recommended")
                self.hear_combo.addItem(label, m)
        self._fade_other_gpu_models(self.hear_combo)
        hear_box.addWidget(hear_lbl)
        hear_box.addWidget(self.hear_combo, 1)
        picker_layout.addLayout(hear_box)

        # Translating model
        trans_box = QHBoxLayout()
        trans_lbl = QLabel(tr("Translating:"))
        self.trans_combo = QComboBox()
        self.trans_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.trans_combo.setMinimumContentsLength(12)
        self.trans_combo.setMinimumWidth(140)
        for m in ("nllb-200-ct2", "qwen3-1.7b-ct2", "hy-mt2-1.8b"):
            if m in local_model.MODELS:
                name, _, _, _ = local_model.MODELS[m]
                sz = local_model.gb(local_model.size(m))
                label = f"{tr(name)} ({sz})"
                if m == "nllb-200-ct2":
                    label += " · " + tr("Recommended")
                self.trans_combo.addItem(label, m)
        trans_box.addWidget(trans_lbl)
        trans_box.addWidget(self.trans_combo, 1)
        picker_layout.addLayout(trans_box)

        self.download_check.toggled.connect(self.models_picker.setVisible)
        models_layout.addWidget(self.models_picker)
        layout.addWidget(self.models_card)

        # Self-hosted online service: no key for now, only the address.
        self.online_card = QFrame()
        self.online_card.setObjectName("card")
        online_layout = QVBoxLayout(self.online_card)
        online_layout.setSpacing(6)
        online_heading = QLabel(tr("Online models"))
        online_heading.setObjectName("title")
        online_layout.addWidget(online_heading)
        online_note = QLabel(tr("Enter the address of your self-hosted server. Add a key only if the server needs one."))
        online_note.setObjectName("dim")
        online_note.setWordWrap(True)
        online_layout.addWidget(online_note)
        address_row = QHBoxLayout()
        address_row.setSpacing(8)
        self.online_url = QLineEdit(services.setting("custom", "url"))
        self.online_url.setPlaceholderText("https://…/v1")
        self.online_url.setAccessibleName(tr("Address"))
        self.online_button = QPushButton(tr("Fetch models"))
        self.online_button.clicked.connect(self.fetch_online_models)
        address_row.addWidget(self.online_url, 1)
        address_row.addWidget(self.online_button)
        online_layout.addLayout(address_row)

        self.online_key_row = QWidget()
        key_row = QHBoxLayout(self.online_key_row)
        key_row.setContentsMargins(0, 0, 0, 0)
        self.online_key = QLineEdit()
        self.online_key.setEchoMode(QLineEdit.Password)
        self.online_key.setPlaceholderText(tr("API key (optional)"))
        self.online_key.setAccessibleName(tr("API key"))
        key_row.addWidget(self.online_key)
        self.online_key_row.setMaximumHeight(0)
        self.online_key_row.setVisible(False)
        online_layout.addWidget(self.online_key_row)
        self._key_visible = False
        self._key_animation = QPropertyAnimation(self.online_key_row, b"maximumHeight", self)
        self._key_animation.setDuration(180)
        self._key_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._key_animation.finished.connect(self._key_animation_finished)

        self.online_result = QLabel()
        self.online_result.setObjectName("dim")
        self.online_result.setWordWrap(True)
        online_layout.addWidget(self.online_result)

        self.online_model_box = QWidget()
        model_layout = QVBoxLayout(self.online_model_box)
        model_layout.setContentsMargins(0, 2, 0, 0)
        model_layout.setSpacing(4)
        for text, attr in (("Hearing model", "online_hear"), ("Translating models", "online_translate")):
            row = QHBoxLayout()
            row.setSpacing(8)
            label = QLabel(tr(text))
            label.setObjectName("dim")
            combo = QComboBox()
            combo.setMinimumContentsLength(12)
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            row.addWidget(label)
            row.addWidget(combo, 1)
            model_layout.addLayout(row)
            setattr(self, attr, combo)
        self.online_model_box.setVisible(False)
        online_layout.addWidget(self.online_model_box)

        layout.addWidget(self.online_card)
        self._online_models: list[str] = []
        self._online_service = ""
        self._name_dialog = None
        self.local_radio.toggled.connect(self._update_mode)
        self.online_url.textChanged.connect(self._url_changed)
        self.online_key.textChanged.connect(lambda _text: self._reset_online_models())
        self.online_hear.currentIndexChanged.connect(self._save_online_choices)
        self.online_translate.currentIndexChanged.connect(self._save_online_choices)
        self.models_fetched.connect(self._models_fetched)
        self._set_key_visible(bool(self.online_url.text().strip()), animate=False)
        self._update_mode()

        # Windows 11 Music Mixer Option
        self.mixer_check = None
        if is_windows_11():
            mixer_card = QFrame()
            mixer_card.setObjectName("card")
            mixer_layout = QVBoxLayout(mixer_card)
            mixer_layout.setSpacing(4)
            self.mixer_check = QCheckBox(tr("Install music mixer"))
            mixer_desc = QLabel(tr("Applies clean music mixing to your microphone stream in VRChat. Requires Administrator approval."))
            mixer_desc.setObjectName("dim")
            mixer_desc.setWordWrap(True)
            mixer_layout.addWidget(self.mixer_check)
            mixer_layout.addWidget(mixer_desc)
            layout.addWidget(mixer_card)

        # Audio Driver Option (only if a signed manifest exists)
        self.driver_check = None
        try:
            manifest = driver_setup.installer_manifest()
        except Exception:
            manifest = None
        if manifest is not None:
            driver_card = QFrame()
            driver_card.setObjectName("card")
            driver_layout = QVBoxLayout(driver_card)
            driver_layout.setSpacing(4)
            self.driver_check = QCheckBox(tr("Install audio capture driver"))
            driver_desc = QLabel(tr("Enables system-wide audio capture for other players' speech."))
            driver_desc.setObjectName("dim")
            driver_desc.setWordWrap(True)
            driver_layout.addWidget(self.driver_check)
            driver_layout.addWidget(driver_desc)
            layout.addWidget(driver_card)

        layout.addStretch(1)

        # Bottom Action Buttons
        footer = QHBoxLayout()
        footer.addStretch(1)

        self.finish_button = QPushButton(tr("Get Started"))
        self.finish_button.clicked.connect(self.apply_setup)
        footer.addWidget(self.finish_button, alignment=Qt.AlignRight)

        layout.addLayout(footer)

    def _update_mode(self, _checked: bool = False) -> None:
        local = self.local_radio.isChecked()
        self.models_card.setVisible(local)
        self.online_card.setVisible(not local)

    def _url_changed(self, text: str) -> None:
        self.online_result.clear()
        self._set_key_visible(bool(text.strip()))
        self._reset_online_models()

    def _reset_online_models(self) -> None:
        if self._name_dialog is not None:
            self._name_dialog.reject()
            self._name_dialog = None
        self._online_service = ""
        self._online_models = []
        self.online_model_box.setVisible(False)
        self.online_hear.clear()
        self.online_translate.clear()

    def _set_key_visible(self, visible: bool, animate: bool = True) -> None:
        if visible == self._key_visible:
            return
        self._key_visible = visible
        self._key_animation.stop()
        if not animate:
            self.online_key_row.setVisible(visible)
            self.online_key_row.setMaximumHeight(16777215 if visible else 0)
            return
        if visible:
            self.online_key_row.setVisible(True)
            self.online_key_row.setMaximumHeight(0)
            self._key_animation.setStartValue(0)
            self._key_animation.setEndValue(max(34, self.online_key_row.sizeHint().height()))
        else:
            self._key_animation.setStartValue(self.online_key_row.height())
            self._key_animation.setEndValue(0)
        self._key_animation.start()

    def _key_animation_finished(self) -> None:
        if not self._key_visible:
            self.online_key_row.setVisible(False)

    def fetch_online_models(self) -> None:
        url = self.online_url.text().strip()
        if not url:
            self.online_result.setText(tr("Enter the server address first."))
            return
        self.online_button.setEnabled(False)
        self.online_result.setText(tr("Fetching models."))
        self._reset_online_models()
        key = self.online_key.text().strip()

        def worker() -> None:
            try:
                models = services.fetch_models("custom", url=url, key=key)
                self.models_fetched.emit(True, models, "")
            except Exception as error:
                self.models_fetched.emit(False, [], str(error))

        threading.Thread(target=worker, daemon=True).start()

    def _models_fetched(self, ok: bool, models, text: str) -> None:
        self.online_button.setEnabled(True)
        if not ok:
            self.online_result.setText("✗ " + tr("Connection issue") + f": {text}")
            return
        self._online_models = list(models)
        if not self._online_models:
            self.online_result.setText(tr("No models found"))
            return
        self._populate_online_models(self._online_models)
        self.online_model_box.setVisible(True)
        self.online_result.setText("✓ " + tr("Found {count} models").format(count=len(self._online_models)))
        self._ask_service_name()

    def _ask_service_name(self) -> None:
        if self._name_dialog is not None:
            return
        url = self.online_url.text().strip()
        default = urlsplit(url).hostname or tr("Self-hosted")
        dialog = ServiceNameDialog(self, default)
        self._name_dialog = dialog
        dialog.accepted.connect(lambda: self._save_named_service(dialog.name_edit.text().strip()))
        dialog.finished.connect(lambda _result: setattr(self, "_name_dialog", None))
        dialog.open()

    def _save_named_service(self, name: str) -> None:
        if not name:
            return
        service = "custom_" + uuid.uuid4().hex
        if not self._write_online_service(service, name=name):
            return
        self._online_service = service
        self.online_result.setText(
            "✓ " + tr("Found {count} models").format(count=len(self._online_models)) +
            " · " + tr("Saved to Services/API") + f": {name}")
        if self.online_radio.isChecked():
            self.settings.hearing = service
            self.settings.translating = service

    def _save_online_choices(self) -> None:
        if self._online_service and self.online_hear.currentData() and self.online_translate.currentData():
            self._save_online_service()

    def _save_online_service(self) -> bool:
        if not self._online_service:
            return False
        return self._write_online_service(self._online_service)

    def _write_online_service(self, service: str, name: str = "") -> bool:
        url = self.online_url.text().strip()
        if not url:
            return False
        values = {"url": url}
        if name:
            values["name"] = name
        key = self.online_key.text().strip()
        if key:
            values["key"] = key
        hear_model = self.online_hear.currentData()
        translate_model = self.online_translate.currentData()
        if hear_model:
            values["hear_model"] = hear_model
        if translate_model:
            values["translate_model"] = translate_model
        try:
            services.save(service, models=self._online_models or None, **values)
        except OSError as error:
            self.online_result.setText("✗ " + tr("Could not save") + f": {error}")
            return False
        return True

    def _populate_online_models(self, models: list[str]) -> None:
        saved = (services.setting("custom", "hear_model"),
                 services.setting("custom", "translate_model"))
        for combo, preferred in zip((self.online_hear, self.online_translate), saved):
            combo.blockSignals(True)
            combo.clear()
            for model in models:
                combo.addItem(model, model)
            index = combo.findData(preferred)
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.blockSignals(False)

    @staticmethod
    def _fade_other_gpu_models(combo: QComboBox) -> None:
        """Grey out the Whisper build that does not match this PC's graphics card."""
        nvidia = local_model.nvidia_card()
        first_enabled = -1
        for index in range(combo.count()):
            model = combo.itemData(index)
            blocked = ((model == "whisper-turbo-vulkan" and nvidia)
                       or (model == "large-v3-turbo" and not nvidia))
            item = combo.model().item(index)
            if item is not None:
                item.setEnabled(not blocked)
                if blocked:
                    item.setForeground(QColor(theme.DIM))
            if not blocked and first_enabled < 0:
                first_enabled = index
        if first_enabled >= 0:
            combo.setCurrentIndex(first_enabled)

    def reject(self) -> None:
        # Required setup completes through Get Started, including when Escape is pressed.
        pass

    def apply_setup(self) -> None:
        if self.local_radio.isChecked():
            self.settings.hearing = "local"
            self.settings.translating = "local"
        else:
            service = self._online_service
            if service:
                self._save_online_service()
            elif self.online_url.text().strip():
                service = services.default_service()
                if self._write_online_service(service):
                    self._online_service = service
            service = service or services.default_service()
            self.settings.hearing = service
            self.settings.translating = service

        if self.local_radio.isChecked():
            hear_m = self.hear_combo.currentData()
            trans_m = self.trans_combo.currentData()
            downloading = self.download_check.isChecked()
            # Equip the chosen models right away: Settings → Models shows and uses them,
            # while the download (if any) finishes in the background.
            for model in (hear_m, trans_m):
                if model and (downloading or local_model.ready(model=model)):
                    local_model.select(model)
            if downloading:
                if hear_m:
                    local_download.shared().start(hear_m)
                if trans_m:
                    local_download.shared().start(trans_m)

        if self.mixer_check and self.mixer_check.isChecked():
            try:
                from vrc import apo_install
                apo_install.install(self.settings.mic_device)
            except Exception as error:
                log.warning("Could not launch mixer install: %s", error)

        self.settings.first_run_done = True
        if self.save_settings:
            self.save_settings()
        self.accept()
