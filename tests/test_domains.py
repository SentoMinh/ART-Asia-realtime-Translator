"""Saved custom domains stay independent throughout hearing, translation and migration."""
from types import SimpleNamespace

import httpx
import numpy as np
import pytest

from engine import services
from engine.speech import SpeechEngine
from engine.stt import CloudHearing
from engine.translators import ServiceTranslator
from ui.config import Settings


def test_only_custom_domains_and_local_models_are_offered():
    services.save("openai", key="old-key")
    services.save("custom_second", name="Second", url="https://second.test/v1")
    assert services.offered() == ("custom", "custom_second")
    assert services.offered(services.HEARING) == ("local", "custom", "custom_second")
    assert services.title("custom_second") == "Second"
    assert Settings().hearing == Settings().translating == "custom"


def test_additional_domain_routes_both_hearing_and_ct2_translation():
    services.save("custom", url="https://first.test/v1", key="first-key")
    services.save("custom_second", url="https://second.test/v1", key="second-key", hear_model="whisper-1")
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"text": "Hello", "language": "en", "translated_text": "Xin chao"})
    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        assert CloudHearing("custom_second", http=http).transcribe(np.zeros(1600, dtype="float32"), "en").text == "Hello"
        assert ServiceTranslator("custom_second", "nllb-200-ct2", http=http).translate("Hello", "vi", "en") == "Xin chao"
    assert [str(r.url) for r in requests] == ["https://second.test/v1/audio/transcriptions", "https://second.test/v1/translate"]
    assert all(r.headers["authorization"] == "Bearer second-key" for r in requests)
    engine = SpeechEngine.__new__(SpeechEngine)
    engine.backend = SimpleNamespace(settings=Settings(hearing="custom_second"))
    engine._engines = {"local": object()}
    assert engine._engine().name == "custom_second"


def test_old_active_provider_is_preserved_as_a_domain():
    services.save("gemini", key="saved-key", translate_model="chosen-model")
    config = Settings(hearing="gemini", translating="gemini").clean()
    assert config.hearing == config.translating == "custom_legacy_gemini"
    assert services.setting(config.hearing, "key") == "saved-key"
    assert services.setting(config.hearing, "url") == services.SERVICES["gemini"].url
    assert services.info(config.hearing).hear_style == "gemini"
    assert services.setting(config.hearing, "translate_model") == "chosen-model"
    services.save(config.hearing, key="updated-key")
    assert services.setting(Settings(hearing="gemini").clean().hearing, "key") == "updated-key"


def test_removing_a_domain_preserves_others_and_resets_stale_selection():
    services.save("custom", url="https://first.test", key="first-key")
    services.save("custom_second", url="https://second.test", key="second-key")
    services.remove_domain("custom_second")
    assert services.offered() == ("custom",)
    assert services.setting("custom", "key") == "first-key"
    assert Settings(hearing="custom_second", translating="custom_second").clean().hearing == "custom"
    with pytest.raises(ValueError):
        services.remove_domain("custom")
