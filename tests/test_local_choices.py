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


def test_removed_large_v3_selection_falls_back_without_deleting_weights():
    old = local_model.folder() / "whisper-v3" / "model.bin"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"existing weights")
    services.save("local", hear_model="large-v3")
    assert "large-v3" not in local_model.MODELS
    assert local_model.selected() == "large-v3-turbo"
    assert old.read_bytes() == b"existing weights"
    local_model.select("phowhisper-small")
    local_model.select("qwen3-1.7b-ct2")
    assert local_model.selected() == "phowhisper-small"
    assert services.translate_models("local") == ["qwen3-1.7b-ct2"]


@pytest.mark.parametrize("model", ["sensevoice", "phowhisper-small", "nllb-200-ct2", "qwen3-1.7b-ct2"])
def test_cpu_models_require_their_own_files_but_no_graphics_card(monkeypatch, model):
    monkeypatch.setattr(local_model, "installed", lambda model=None: True)
    monkeypatch.setattr(local_model, "nvidia_card", lambda: False)
    assert "not downloaded" in local_model.missing(model)
    monkeypatch.setattr(local_model, "ready", lambda root=None, model=None: model != "large-v3-turbo")
    assert not local_model.missing(model)
    assert "NVIDIA" in local_model.missing("large-v3-turbo")


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
    local_model.select("phowhisper-small")
    assert hearing.transcribe([], "vi") == "phowhisper-small"
    assert made == ["large-v3-turbo", "sensevoice", "phowhisper-small"]


def test_hearing_close_frees_the_recognizer_and_a_later_use_reloads_it(monkeypatch):
    made, closed = [], []
    def make(name):
        made.append(name)
        return SimpleNamespace(load=lambda: None, close=lambda: closed.append(name),
                               transcribe=lambda *a, **kw: name)
    monkeypatch.setattr(local_inference, "LocalWhisper", make)
    monkeypatch.setattr(local_inference, "LocalSenseVoice", lambda: make("sensevoice"))
    hearing = local_inference.LocalHearing()
    assert hearing.transcribe([], "en") == "large-v3-turbo"
    assert hearing.close() is True
    assert closed == ["large-v3-turbo"]
    assert hearing.close() is False                  # already free: nothing to do
    assert hearing.transcribe([], "en") == "large-v3-turbo"
    assert made == ["large-v3-turbo", "large-v3-turbo"]


def test_releasing_local_translation_frees_every_resident_model():
    closed = []
    class Native:
        def close(self):
            closed.append(True)
    engines = (local_inference.translator, local_inference.qwen_translator, local_inference.hy_mt_translator)
    for engine in engines:
        engine._model, engine._tokenizer = Native(), SimpleNamespace()
    assert local_inference.release_local_translation() is True
    assert closed == [True, True, True]
    for engine in engines:
        assert engine._model is None and engine._tokenizer is None
    assert local_inference.release_local_translation() is False
    assert closed == [True, True, True]


def test_phowhisper_loads_its_own_download_on_cpu_not_turbo(monkeypatch):
    from engine import stt
    sources = []
    monkeypatch.setattr(local_model, "missing", lambda model=None: "")
    monkeypatch.setattr(local_model, "ready", lambda root=None, model=None: True)
    monkeypatch.setattr(stt, "_add_gpu_libraries", lambda: pytest.fail("PhoWhisper must not load CUDA"))
    def create(source, **kwargs):
        sources.append(source)
        assert kwargs == dict(device="cpu", compute_type="int8", cpu_threads=1, num_workers=1)
        return SimpleNamespace(transcribe=lambda *a, **kw: ([], None))
    monkeypatch.setattr(stt, "whisper_class", lambda: create)
    stt.LocalWhisper("phowhisper-small").load()
    assert sources == [str(local_model.model_folder("phowhisper-small"))]
    assert sources[0] != str(local_model.model_folder("large-v3-turbo"))


def test_phowhisper_filters_other_languages_and_keeps_vietnamese(monkeypatch):
    from engine import stt
    model = stt.LocalWhisper("phowhisper-small")
    monkeypatch.setattr(model, "load", lambda: None)
    monkeypatch.setattr(model, "_run", lambda *args: ("Tôi muốn thử lại.", SimpleNamespace(language="vi")))
    assert model.transcribe([], "vi").text == "Tôi muốn thử lại."
    assert model.transcribe([], None).lang == "vi"
    with pytest.raises(SttError, match="supports Vietnamese"):
        model.transcribe([], "en")
    monkeypatch.setattr(model, "_run", lambda *args: ("Hello", SimpleNamespace(language="en")))
    assert model.transcribe([], None).text == ""


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


@pytest.mark.parametrize("model_id,engine_type,runtime", [
    ("nllb-200-ct2", local_inference.LocalTranslator, "Translator"),
    ("qwen3-1.7b-ct2", local_inference.LocalQwenTranslator, "Generator"),
])
def test_local_translation_prepares_selected_weights_once_without_generating(monkeypatch, model_id, engine_type, runtime):
    creates, inference = [], []
    tokenizer = SimpleNamespace(
        encode=lambda text, **kwargs: SimpleNamespace(tokens=text.split()),
        token_to_id=lambda token: token,
        decode=lambda tokens, **kwargs: " ".join(t for t in tokens if t != "</s>"))
    def run(*args, **kwargs):
        inference.append(True)
        return [SimpleNamespace(hypotheses=[["vie_Latn", "Xin", "chào", "</s>"]],
                                sequences=[["Xin", "chào", "<|im_end|>"]])]
    def create(root, **kwargs):
        creates.append((root, kwargs))
        return SimpleNamespace(translate_batch=run, generate_batch=run)
    monkeypatch.setattr(local_model, "missing", lambda model: "")
    monkeypatch.setitem(sys.modules, "ctranslate2", SimpleNamespace(**{runtime: create}))
    monkeypatch.setitem(sys.modules, "tokenizers", SimpleNamespace(Tokenizer=SimpleNamespace(from_file=lambda path: tokenizer)))
    model = engine_type()
    model.prepare()
    assert creates == [(str(local_model.model_folder(model_id)),
                        dict(device="cpu", compute_type="int8", inter_threads=1, intra_threads=1))]
    assert not inference
    model.prepare()
    assert model.translate("Hello", "vi", "en") == "Xin chào"
    assert len(creates) == 1 and len(inference) == 1


def test_local_preparation_failure_is_retryable_on_first_translation(monkeypatch):
    monkeypatch.setattr(local_model, "missing", lambda model: "")
    creates = []
    def create(*args, **kwargs):
        creates.append(True)
        raise OSError("temporary model load failure")
    monkeypatch.setitem(sys.modules, "ctranslate2", SimpleNamespace(Translator=create))
    monkeypatch.setitem(sys.modules, "tokenizers", SimpleNamespace(Tokenizer=SimpleNamespace(from_file=lambda path: object())))
    model = local_inference.LocalTranslator()
    model.prepare()  # A background preload failure must not kill the typed worker.
    assert len(creates) == 1 and model._model is None
    with pytest.raises(TranslateError, match="temporary model load failure"):
        model.translate("Hello", "vi", "en")
    assert len(creates) == 2


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
    chain = ServiceChain(lambda: "local")
    assert chain.translate("Hello", "vi", "en") == "Xin chao"
    assert chain.last_used == "local:nllb-200-ct2"
    assert called == [("Hello", "vi", "en")]


def test_translation_switch_routes_all_chains_and_keeps_hearing_selection(monkeypatch):
    monkeypatch.setattr(local_inference.translator, "translate", lambda *a, **kw: "NLLB")
    monkeypatch.setattr(local_inference.qwen_translator, "translate", lambda *a, **kw: "Qwen")
    monkeypatch.setattr(local_inference.hy_mt_translator, "translate", lambda *a, **kw: "Hy-MT2")
    typed, speech = ServiceChain(lambda: "local"), ServiceChain(lambda: "local")
    local_model.select("sensevoice")
    for model, expected in (("nllb-200-ct2", "NLLB"), ("qwen3-1.7b-ct2", "Qwen"),
                            ("hy-mt2-1.8b", "Hy-MT2"), ("nllb-200-ct2", "NLLB")):
        local_model.select(model)
        for chain in (typed, speech):
            assert chain.translate("Hello", "vi", "en") == expected
            assert chain.last_used == f"local:{model}"
        assert local_model.selected() == "sensevoice"


def test_hy_mt_uses_tencents_prompt_and_greedy_llama_cpp(monkeypatch):
    calls = []

    class FakeLlama:
        def __init__(self, path, **options):
            calls.append((path, options))

        def tokenize(self, data, add_bos=False):
            return list(data[:4])

        def create_chat_completion(self, messages, **options):
            calls.append((messages, options))
            return {"choices": [{"finish_reason": "stop", "message": {"content": "  Xin   chào  "}}]}

    monkeypatch.setattr(local_model, "missing", lambda model: "")
    monkeypatch.setitem(sys.modules, "llama_cpp", SimpleNamespace(Llama=FakeLlama))
    monkeypatch.setattr(local_inference.translator, "_model", object())
    engine = local_inference.LocalHyMTTranslator()
    assert engine.translate("等一下", "vi", "zh") == "Xin chào"
    path, options = calls[0]
    assert path == str(local_model.model_folder("hy-mt2-1.8b") / "model.gguf")
    assert options["n_gpu_layers"] == 0 and options["n_threads"] == options["n_threads_batch"] == 1
    messages, decoding = calls[1]
    assert messages == [{"role": "user", "content":
                         "将以下文本翻译为越南语，注意只需要输出翻译后的结果，不要额外解释：\n\n等一下"}]
    assert decoding["temperature"] == 0.0 and decoding["top_k"] == 1 and decoding["max_tokens"] == 512
    assert local_inference.translator._model is None
    english = local_inference.hy_mt_prompt("Wait", "vi", "en")
    assert english.startswith("Translate the following text into Vietnamese.")


@pytest.mark.parametrize("answer,finish,target,error", [
    ("Xin chào", "length", "vi", "did not finish"),
    ("", "stop", "vi", "did not return"),
    ("你好", "stop", "vi", "instead of translating"),
    ("Hello", "stop", "ja", "requested language"),
    ("word " * 64, "stop", "vi", "kept repeating"),
])
def test_hy_mt_rejects_an_unfinished_or_wrong_language_answer(monkeypatch, answer, finish, target, error):
    engine = local_inference.LocalHyMTTranslator()
    engine._model = SimpleNamespace(
        tokenize=lambda data, add_bos=False: data.split(),
        create_chat_completion=lambda *a, **kw: {"choices": [{"finish_reason": finish,
                                                              "message": {"content": answer}}]})
    monkeypatch.setattr(local_model, "missing", lambda model: "")
    with pytest.raises(TranslateError, match=error) as caught:
        engine.translate("Hello", target, "en")
    assert caught.value.wait == 0


def test_hy_mt_shortcuts_and_input_limit_do_not_generate(monkeypatch):
    engine = local_inference.LocalHyMTTranslator()
    engine._model = SimpleNamespace(tokenize=lambda data, add_bos=False: data.split())
    monkeypatch.setattr(local_model, "missing", lambda model: "")
    assert engine.translate("Hello", "en", "en") == "Hello"
    assert engine.translate("。", "vi", "zh") == "。"
    with pytest.raises(TranslateError, match="too long"):
        engine.translate("word " * 1100, "vi", "en")
    monkeypatch.setattr(local_model, "missing", lambda model: "download first")
    with pytest.raises(TranslateError, match="download first") as caught:
        engine.translate("Hello", "vi", "en")
    assert caught.value.wait == 0


def test_local_chain_uses_hy_mt_when_selected(monkeypatch):
    monkeypatch.setattr(local_inference.hy_mt_translator, "translate", lambda *a, **kw: "Hy-MT2")
    local_model.select("hy-mt2-1.8b")
    chain = ServiceChain(lambda: "local")
    assert chain.translate("Hello", "vi", "en") == "Hy-MT2"
    assert chain.last_used == "local:hy-mt2-1.8b"
