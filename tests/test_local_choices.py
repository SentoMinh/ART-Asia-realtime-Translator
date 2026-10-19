"""Local models keep independent selections, downloads and inference routes."""
import hashlib
import sys
from types import SimpleNamespace

import pytest

from engine import local_inference, local_model, services
from engine.stt import SttError
from engine.translators import ServiceChain
from vrc.translate import TranslateError


def test_selections_preserve_the_other_role_and_reject_old_values():
    local_model.select("sensevoice")
    local_model.select("nllb-200-ct2")
    assert local_model.selected() == "sensevoice"
    assert local_model.selected("translating") == "nllb-200-ct2"
    services.save("local", hear_model="nllb-200-ct2")
    assert local_model.selected() == "large-v3-turbo"


@pytest.mark.parametrize("model", ["sensevoice", "nllb-200-ct2"])
def test_cpu_models_require_their_own_files_but_no_graphics_card(monkeypatch, model):
    monkeypatch.setattr(local_model, "installed", lambda model=None: True)
    monkeypatch.setattr(local_model, "nvidia_card", lambda: False)
    assert "not downloaded" in local_model.missing(model)
    monkeypatch.setattr(local_model, "ready", lambda root=None, model=None: model != "large-v3")
    assert not local_model.missing(model)
    assert "NVIDIA" in local_model.missing("large-v3")


def test_download_resumes_only_the_chosen_models_partial_file(monkeypatch, tmp_path):
    from test_local_model import Http
    data = b"model bytes"
    part = local_model.Part("https://files.test/model.bin", len(data), hashlib.sha256(data).hexdigest(), "nllb/model.bin")
    monkeypatch.setattr(local_model, "parts", lambda model=None: (part,))
    waiting = tmp_path / "downloading"
    for name, contents in (("nllb-200-ct2", data[:3]), ("large-v3", b"other model")):
        (waiting / name).mkdir(parents=True)
        (waiting / name / "model.bin").write_bytes(contents)
    http = Http({part.url: data})
    local_model.download(model="nllb-200-ct2", root=tmp_path, http=http)
    assert http.asked == [("model.bin", 3)]
    assert (tmp_path / "nllb/model.bin").read_bytes() == data
    assert (waiting / "large-v3/model.bin").read_bytes() == b"other model"


def test_hearing_switches_saved_models_and_reuses_the_current_engine(monkeypatch):
    made = []
    def make(name):
        made.append(name)
        return SimpleNamespace(load=lambda: None, transcribe=lambda *a, **kw: name)
    monkeypatch.setattr(local_inference, "LocalWhisper", make)
    monkeypatch.setattr(local_inference, "LocalSenseVoice", lambda: make("sensevoice"))
    hearing = local_inference.LocalHearing()
    assert hearing.transcribe([], "en") == "large-v3-turbo"
    local_model.select("sensevoice")
    assert hearing.transcribe([], "en") == "sensevoice"
    assert hearing.transcribe([], None) == "sensevoice"
    local_model.select("large-v3")
    assert hearing.transcribe([], "vi") == "large-v3"
    assert made == ["large-v3-turbo", "sensevoice", "large-v3"]


def test_whisper_large_v3_loads_its_own_download_not_turbo(monkeypatch):
    from engine import stt
    sources = []
    monkeypatch.setattr(local_model, "missing", lambda model=None: "")
    monkeypatch.setattr(local_model, "ready", lambda root=None, model=None: True)
    monkeypatch.setattr(stt, "_add_gpu_libraries", lambda: None)
    def create(source, **kwargs):
        sources.append(source)
        return SimpleNamespace(transcribe=lambda *a, **kw: ([], None))
    monkeypatch.setattr(stt, "whisper_class", lambda: create)
    stt.LocalWhisper("large-v3").load()
    assert sources == [str(local_model.model_folder("large-v3"))]
    assert sources[0] != str(local_model.model_folder("large-v3-turbo"))


def test_sensevoice_reuses_cpu_recognizer_and_rejects_unsupported_language(monkeypatch):
    calls = []
    stream = SimpleNamespace(accept_waveform=lambda rate, samples: calls.append(rate),
                             result=SimpleNamespace(text="Hello there.", lang="<|en|>"))
    recognizer = SimpleNamespace(create_stream=lambda: stream, decode_stream=lambda stream: None)
    def create(**kwargs):
        calls.append(kwargs)
        return recognizer
    monkeypatch.setitem(sys.modules, "sherpa_onnx", SimpleNamespace(OfflineRecognizer=SimpleNamespace(from_sense_voice=create)))
    monkeypatch.setattr(local_model, "missing", lambda model=None: "")
    model = local_inference.LocalSenseVoice()
    assert model.transcribe([], "en").lang == "en"
    assert model.transcribe([], None).text == "Hello there."
    assert len([call for call in calls if isinstance(call, dict)]) == 1
    assert calls[0]["provider"] == "cpu" and calls[0]["language"] == "auto"
    assert calls[1:] == [16000, 16000]
    with pytest.raises(SttError, match="choose Whisper"):
        model.transcribe([], "vi")


def test_nllb_language_prefix_and_decoding(monkeypatch):
    calls = []
    def translate(tokens, **kwargs):
        calls.append((tokens, kwargs))
        return [SimpleNamespace(hypotheses=[["vie_Latn", "Xin", "chao", "</s>"]])]
    translator = local_inference.LocalTranslator()
    translator._model = SimpleNamespace(translate_batch=translate)
    translator._tokenizer = SimpleNamespace(
        encode=lambda text, add_special_tokens: SimpleNamespace(tokens=["Hello"]),
        token_to_id=lambda token: {"Xin": 1, "chao": 2, "</s>": 3}[token],
        decode=lambda ids, skip_special_tokens: "Xin chao" if ids == [1, 2, 3] and skip_special_tokens else "")
    monkeypatch.setattr(local_model, "missing", lambda model=None: "")
    assert translator.translate("Hello", "vi", "en") == "Xin chao"
    assert calls == [([["eng_Latn", "Hello", "</s>"]], {"target_prefix": [["vie_Latn"]], "beam_size": 1})]
    assert translator.translate("Hello", "en", "en") == "Hello"
    with pytest.raises(TranslateError, match="does not support"):
        translator.translate("Hello", "invalid", "en")


def test_missing_translation_can_retry_immediately_after_download(monkeypatch):
    monkeypatch.setattr(local_model, "missing", lambda model=None: "download first")
    with pytest.raises(TranslateError) as error:
        local_inference.LocalTranslator().translate("Hello", "vi", "en")
    assert error.value.wait == 0


def test_local_translation_chain_uses_shared_runtime_without_http(monkeypatch):
    called = []
    monkeypatch.setattr(local_inference.translator, "translate", lambda *a, **kw: called.append(a) or "Xin chao")
    chain = ServiceChain(lambda: "local", addons=[])
    assert chain.translate("Hello", "vi", "en") == "Xin chao"
    assert chain.last_used == "local:nllb-200-ct2"
    assert called == [("Hello", "vi", "en")]
