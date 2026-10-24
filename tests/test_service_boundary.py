"""A saved service choice never imports or calls legacy per-PC translator add-ons."""
from pathlib import Path
import os

import pytest

from engine import local_inference, services
from engine.translators import ServiceChain, ServiceTranslator
from vrc.translate import TranslateError


@pytest.fixture
def legacy_addon(tmp_path):
    marker = tmp_path / "addon-imported"
    folder = Path(os.environ["APPDATA"]) / "VRChat-Translator/addons"
    folder.mkdir(parents=True)
    addon = folder / "gemini.py"
    addon.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
        "from vrc.translate import TranslateError\n"
        "class Gemini:\n"
        "    def prepare(self): pass\n"
        "    def translate(self, *args, **kwargs):\n"
        "        raise TranslateError(\"Gemini's per-minute limit was reached\")\n"
        "def translators(): return [('gemini', Gemini())]\n", encoding="utf-8")
    return marker, addon


@pytest.mark.parametrize("service", ["custom", "custom_second", "openai", "local"])
def test_service_failure_keeps_its_error_without_loading_legacy_addons(service, legacy_addon, monkeypatch):
    if service != "local":
        services.save(service, url="https://selected.test/v1", key="test", translate_model="chosen-model")
    calls = []
    def fail(*args, **kwargs):
        calls.append(True)
        raise TranslateError("Selected model is unavailable")
    monkeypatch.setattr(ServiceTranslator, "translate", fail)
    monkeypatch.setattr(local_inference.translator, "translate", fail)
    chain = ServiceChain(lambda: service)
    chain.prepare()
    for target in ("en", "vi"):
        with pytest.raises(TranslateError, match="^Selected model is unavailable$"):
            chain.translate("test", target, "zh", heard=True)
    marker, addon = legacy_addon
    assert calls == [True]  # Cooldown preserves the same error without another request.
    assert not marker.exists() and addon.exists()
    assert chain.last_used == ""


def test_explicit_models_share_only_the_selected_domain_and_switching_keeps_boundary(legacy_addon, monkeypatch):
    services.save("custom", url="https://selected.test/v1", translate_model="busy, working")
    services.save("custom_second", url="https://second.test/v1", translate_model="other")
    calls, switches = [], []
    def translate(self, *args, **kwargs):
        calls.append((self.service, self.model))
        if self.model == "busy":
            raise TranslateError("busy")
        return "translation"
    monkeypatch.setattr(ServiceTranslator, "translate", translate)
    monkeypatch.setattr(local_inference.translator, "translate", lambda *a, **kw: "local translation")
    selected = ["custom"]
    chain = ServiceChain(lambda: selected[0], on_switch=switches.append)
    assert chain.translate("hello", "vi", "en") == "translation"
    assert calls == [("custom", "busy"), ("custom", "working")]
    assert all(name == "custom:working" for name in switches)
    selected[0] = "local"
    assert chain.translate("hello", "vi", "en") == "local translation"
    selected[0] = "custom_second"
    assert chain.translate("hello", "vi", "en") == "translation"
    assert calls[-1] == ("custom_second", "other")
    assert chain.names() == ["custom_second:other"]
    marker, addon = legacy_addon
    assert not marker.exists() and addon.exists()
