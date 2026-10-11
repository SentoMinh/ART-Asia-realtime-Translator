"""Model discovery and status must work in both release editions."""
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget

from engine import services
from engine.translators import ServiceChain, ServiceTranslator
from ui.config import Settings
from ui.settings_window import ServiceDialog, SettingsWindow
from vrc.translate import TranslateError


@pytest.fixture
def model_ui(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv("APPDATA", str(tmp_path))
    yield app


@pytest.mark.parametrize("friends", [False, True])
def test_discover_pick_and_save_in_both_editions(model_ui, monkeypatch, friends):
    monkeypatch.setattr(services, "dev", lambda: {"hear_model": "friend-hearing"} if friends else {})
    requests = []

    def respond(request):
        requests.append(request)
        if request.url.path == "/models":
            return httpx.Response(404)
        return httpx.Response(200, json={"data": [{"id": "whisper-custom"}, {"id": "chat-custom"}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        dialog = ServiceDialog("custom", http=http)
        dialog.url.setText("https://models.example")
        dialog.fetch_models()
        assert "Found 2 models" in dialog.result.text()
        assert [r.url.path for r in requests] == ["/models", "/v1/models"]
        assert all("authorization" not in r.headers for r in requests)
        dialog.hear_picker.setCurrentIndex(dialog.hear_picker.findData("whisper-custom"))
        dialog.translate_picker.setCurrentIndex(dialog.translate_picker.findData("chat-custom"))
        dialog.save()
        assert services.setting("custom", "hear_model") == "whisper-custom"
        assert services.translate_models("custom") == ["chat-custom"]
        assert not services.missing("custom")
        dialog.deleteLater()


def test_fetch_error_can_be_retried(model_ui, monkeypatch):
    dialog = ServiceDialog("custom")
    def fail(*args, **kwargs):
        raise TimeoutError("timed out")
    monkeypatch.setattr(services, "fetch_models", fail)
    dialog.fetch_models()
    assert "Timed out" in dialog.result.text()
    assert dialog.fetch_btn.isEnabled()
    monkeypatch.setattr(services, "fetch_models", lambda *a, **kw: ["recovered"])
    dialog.fetch_models()
    assert dialog.hear_picker.findData("recovered") > 0
    dialog.deleteLater()


@pytest.mark.parametrize("friends", [False, True])
def test_labels_refresh_and_ignore_old_configuration(model_ui, monkeypatch, friends):
    monkeypatch.setattr(services, "dev", lambda: {"hear_model": "friend-hearing"} if friends else {})
    settings = Settings(hearing="custom", translating="custom")
    services.save("custom", url="https://models.example/v1", hear_model="hearing<one>", translate_model="first, second")
    parent = QWidget()
    parent.backend = SimpleNamespace()
    dialog = SettingsWindow(settings, parent)
    assert "hearing&lt;one&gt;" in dialog._hearing_desc.text()
    assert "Currently in use:" in dialog._translating_desc.text()
    assert "first" in dialog._translating_desc.text()
    parent.backend._translator = SimpleNamespace(last_result=(1, "custom", ("first", "second"), "custom:second"))
    parent.backend.speech_engine = SimpleNamespace(_translator=SimpleNamespace(
        last_result=(2, "custom", ("first", "second"), "custom:first")))
    dialog._update_model_labels()
    assert "first" in dialog._translating_desc.text()
    parent.backend._translator.last_result = (3, "custom", ("first", "second"), "custom:second")
    from PySide6.QtTest import QTest
    QTest.qWait(650)
    assert "second" in dialog._translating_desc.text()
    services.save("custom", hear_model="new-hearing", translate_model="new-model")
    dialog.sync()
    assert "new-hearing" in dialog._hearing_desc.text()
    assert "new-model" in dialog._translating_desc.text()
    assert "second" not in dialog._translating_desc.text()
    parent.deleteLater()


def test_successful_fallback_records_the_model_for_the_ui(model_ui, monkeypatch):
    services.save("custom", url="https://models.example/v1", translate_model="first, second")
    def translate(self, *args, **kwargs):
        if self.model == "first":
            raise TranslateError("unavailable")
        return "translated"
    monkeypatch.setattr(ServiceTranslator, "translate", translate)
    chain = ServiceChain(lambda: "custom", addons=[])
    assert chain.translate("hello", "vi") == "translated"
    assert chain.last_result[1:] == ("custom", ("first", "second"), "custom:second")
