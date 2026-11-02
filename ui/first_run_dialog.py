"""Initial setup dialog shown only on the first run of the application.

Lets the user choose between online services (lightweight default) or local models,
and optionally queue local models or install the music mixer.
"""
from __future__ import annotations

import logging
import sys
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from engine import local_model, services
from vrc import driver_setup

from . import local_download, theme
from .config import Settings
from .i18n import tr

log = logging.getLogger("ui.first_run")


def is_windows_11() -> bool:
    if sys.platform != "win32":
        return False
    try:
        return sys.getwindowsversion().build >= 22000
    except (AttributeError, OSError):
        return False


class FirstRunDialog(QDialog):
    def __init__(self, parent=None, settings: Settings | None = None, save: Callable[[], None] | None = None):
        super().__init__(parent)
        self.settings = settings or Settings()
        self.save_settings = save
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setObjectName("settings")
        self.setWindowTitle(tr("Welcome to VRChat Translator"))
        self.setMinimumWidth(500)
        self.resize(540, 460)

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
        self.online_radio = QRadioButton(tr("Online services (Recommended · fast, lightweight, ready immediately)"))
        self.local_radio = QRadioButton(tr("Local AI models (Offline privacy, runs on your PC)"))
        self.mode_group.addButton(self.online_radio)
        self.mode_group.addButton(self.local_radio)
        self.online_radio.setChecked(True)

        mode_layout.addWidget(self.online_radio)
        mode_layout.addWidget(self.local_radio)
        layout.addWidget(mode_card)

        # Optional Local Models Download Card
        models_card = QFrame()
        models_card.setObjectName("card")
        models_layout = QVBoxLayout(models_card)
        models_layout.setSpacing(8)

        self.download_check = QCheckBox(tr("Download local AI models"))
        models_layout.addWidget(self.download_check)

        self.models_picker = QWidget()
        picker_layout = QVBoxLayout(self.models_picker)
        picker_layout.setContentsMargins(18, 4, 0, 4)
        picker_layout.setSpacing(8)

        # Hearing model
        hear_box = QHBoxLayout()
        hear_lbl = QLabel(tr("Hearing:"))
        self.hear_combo = QComboBox()
        for m in ("whisper-turbo-vulkan", "large-v3-turbo", "sensevoice", "phowhisper-small"):
            if m in local_model.MODELS:
                name, _, _, _ = local_model.MODELS[m]
                sz = local_model.gb(local_model.size(m))
                self.hear_combo.addItem(f"{tr(name)} ({sz})", m)
        hear_box.addWidget(hear_lbl)
        hear_box.addWidget(self.hear_combo, 1)
        picker_layout.addLayout(hear_box)

        # Translating model
        trans_box = QHBoxLayout()
        trans_lbl = QLabel(tr("Translating:"))
        self.trans_combo = QComboBox()
        for m in ("nllb-200-ct2", "qwen3-1.7b-ct2", "hy-mt2-1.8b"):
            if m in local_model.MODELS:
                name, _, _, _ = local_model.MODELS[m]
                sz = local_model.gb(local_model.size(m))
                self.trans_combo.addItem(f"{tr(name)} ({sz})", m)
        trans_box.addWidget(trans_lbl)
        trans_box.addWidget(self.trans_combo, 1)
        picker_layout.addLayout(trans_box)

        self.models_picker.setVisible(False)
        self.download_check.toggled.connect(self.models_picker.setVisible)
        models_layout.addWidget(self.models_picker)
        layout.addWidget(models_card)

        # Windows 11 Music Mixer Option
        self.mixer_check = None
        if is_windows_11():
            mixer_card = QFrame()
            mixer_card.setObjectName("card")
            mixer_layout = QVBoxLayout(mixer_card)
            mixer_layout.setSpacing(4)
            self.mixer_check = QCheckBox(tr("Install microphone music mixer (Windows 11)"))
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
        self.skip_button = QPushButton(tr("Skip"))
        self.skip_button.setObjectName("plain")
        self.skip_button.clicked.connect(self.skip_setup)
        footer.addWidget(self.skip_button, alignment=Qt.AlignLeft)

        footer.addStretch(1)

        self.finish_button = QPushButton(tr("Get Started"))
        self.finish_button.clicked.connect(self.apply_setup)
        footer.addWidget(self.finish_button, alignment=Qt.AlignRight)

        layout.addLayout(footer)

    def skip_setup(self) -> None:
        self.settings.first_run_done = True
        if self.save_settings:
            self.save_settings()
        self.accept()

    def apply_setup(self) -> None:
        if self.local_radio.isChecked():
            self.settings.hearing = "local"
            self.settings.translating = "local"
        else:
            self.settings.hearing = services.default_service()
            self.settings.translating = services.default_service()

        if self.download_check.isChecked():
            hear_m = self.hear_combo.currentData()
            trans_m = self.trans_combo.currentData()
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
