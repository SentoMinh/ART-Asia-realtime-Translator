"""Dialog asking user before switching models or recommending Local Model."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout, QWidget)

from engine import local_model, services

from .config import Settings
from .i18n import tr


def get_ready_models(category: str, exclude: str = "") -> list[tuple[str, str, str]]:
    """Returns list of (service_id, model_name, display_label) for already set up models."""
    results = []
    choices = services.offered(services.HEARING if category == "hearing" else services.TRANSLATING)
    for svc in choices:
        if svc == exclude:
            continue
        if svc == "local":
            if category == "translating":
                model = local_model.selected(category)
                if not local_model.missing(model):
                    results.append((svc, model, local_model.MODELS[model][0]))
            continue
        if services.ready(svc):
            if category == "hearing":
                model = services.setting(svc, "hear_model")
                if not model and svc in services.SERVICES:
                    model = services.SERVICES[svc].hear_model
            else:
                models = services.translate_models(svc)
                model = models[0] if models else services.setting(svc, "translate_model")
                if not model and svc in services.SERVICES:
                    model = services.SERVICES[svc].translate_model
            title = services.title(svc)
            label = f"{model} ({title})" if model else title
            results.append((svc, model, label))
    return results


class SwitchModelDialog(QDialog):
    """Asks the user before switching model, or recommends downloading/switching to Local Model."""
    switched = Signal(str, str, str)       # category, service, model_name
    declined = Signal()
    open_local_download = Signal()
    open_settings_page = Signal(str)       # page_name

    def __init__(self, category: str, failed_service: str, settings: Settings,
                 reason: str = "", parent=None):
        super().__init__(parent)
        self.category = category
        self.failed_service = failed_service
        self.settings = settings
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setObjectName("settings")
        self.setWindowTitle(tr("Switch Model"))
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)

        heading = QLabel(tr("Switch Model"))
        heading.setObjectName("heading")
        layout.addWidget(heading)

        category_title = tr("Hearing") if category == "hearing" else tr("Translating")
        failed_title = services.title(failed_service) if failed_service in services.SERVICES else failed_service
        info_text = tr("The {category} model for {service} is unavailable.").format(
            category=category_title, service=failed_title
        )
        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        if reason:
            dim_reason = QLabel(reason)
            dim_reason.setObjectName("dim")
            dim_reason.setWordWrap(True)
            layout.addWidget(dim_reason)

        candidates = get_ready_models(category, exclude=failed_service)
        self.candidates = candidates

        buttons = QHBoxLayout()
        cancel = QPushButton(tr("Cancel"))
        cancel.setObjectName("plain")
        cancel.clicked.connect(self._on_cancel)

        if candidates:
            # Already set up model(s) exist: ask user if want to switch
            if len(candidates) == 1:
                svc, model, label = candidates[0]
                prompt = QLabel(tr("Would you like to switch to {model}?").format(model=label))
                prompt.setWordWrap(True)
                layout.addWidget(prompt)

                switch_btn = QPushButton(tr("Switch to {model}").format(model=model or label))
                switch_btn.clicked.connect(lambda: self._on_switch(svc, model))
                buttons.addStretch(1)
                buttons.addWidget(cancel)
                buttons.addWidget(switch_btn)
            else:
                prompt = QLabel(tr("Would you like to switch to an already set up model?"))
                prompt.setWordWrap(True)
                layout.addWidget(prompt)

                self.combo = QComboBox()
                for svc, model, label in candidates:
                    self.combo.addItem(label, (svc, model))
                layout.addWidget(self.combo)

                switch_btn = QPushButton(tr("Switch"))
                switch_btn.clicked.connect(self._on_combo_switch)
                buttons.addStretch(1)
                buttons.addWidget(cancel)
                buttons.addWidget(switch_btn)

            # If hearing, also offer Local Model as option if ready
            if category == "hearing" and not local_model.missing():
                local_btn = QPushButton(tr("Or switch to Local Model"))
                local_btn.setObjectName("plain")
                local_btn.clicked.connect(lambda: self._on_switch("local", local_model.MODELS[local_model.selected()][0]))
                buttons.insertWidget(0, local_btn)

        else:
            # None exists: recommend to download/switch to Local Model
            if category == "hearing":
                no_model_label = QLabel(tr("No other set up model was found."))
                no_model_label.setObjectName("dim")
                layout.addWidget(no_model_label)

                if not local_model.missing():
                    rec_label = QLabel(tr("You can switch to your downloaded local hearing model."))
                    rec_label.setWordWrap(True)
                    layout.addWidget(rec_label)

                    switch_btn = QPushButton(tr("Switch to Local Model"))
                    switch_btn.clicked.connect(lambda: self._on_switch("local", local_model.MODELS[local_model.selected()][0]))
                    buttons.addStretch(1)
                    buttons.addWidget(cancel)
                    buttons.addWidget(switch_btn)
                else:
                    rec_label = QLabel(tr("Choose a local hearing model to download and run on this PC."))
                    rec_label.setWordWrap(True)
                    layout.addWidget(rec_label)

                    dl_btn = QPushButton(tr("Download Local Model"))
                    dl_btn.clicked.connect(self._on_download_local)
                    buttons.addStretch(1)
                    buttons.addWidget(cancel)
                    buttons.addWidget(dl_btn)
            else:
                no_model_label = QLabel(tr("No other set up translating model was found."))
                no_model_label.setObjectName("dim")
                layout.addWidget(no_model_label)

                rec_label = QLabel(tr("Please set up a translation service in Settings → Models."))
                rec_label.setWordWrap(True)
                layout.addWidget(rec_label)

                settings_btn = QPushButton(tr("Open Settings"))
                settings_btn.clicked.connect(self._on_open_settings)
                buttons.addStretch(1)
                buttons.addWidget(cancel)
                buttons.addWidget(settings_btn)

        layout.addLayout(buttons)

    def _on_switch(self, service: str, model_name: str) -> None:
        self.switched.emit(self.category, service, model_name)
        self.accept()

    def _on_combo_switch(self) -> None:
        svc, model = self.combo.currentData()
        self.switched.emit(self.category, svc, model)
        self.accept()

    def _on_download_local(self) -> None:
        self.open_local_download.emit()
        self.accept()

    def _on_open_settings(self) -> None:
        self.open_settings_page.emit("Models")
        self.accept()

    def _on_cancel(self) -> None:
        self.declined.emit()
        self.reject()
