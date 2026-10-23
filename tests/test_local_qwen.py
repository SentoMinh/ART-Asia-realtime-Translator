from types import SimpleNamespace
import sys

import pytest

from engine import local_inference, local_model
from vrc.translate import TranslateError


@pytest.fixture
def qwen(monkeypatch):
    calls = []
    engine = local_inference.LocalQwenTranslator()
    def encode(text, add_special_tokens=False):
        calls.append(text)
        return SimpleNamespace(tokens=text.split())
    engine._tokenizer = SimpleNamespace(encode=encode, token_to_id=lambda token: token,
                                       decode=lambda ids, **kw: " ".join(ids))
    def generate(tokens, **kwargs):
        calls.append(kwargs)
        return [SimpleNamespace(sequences=[["Xin", "chào", "<|im_end|>"]])]
    engine._model = SimpleNamespace(generate_batch=generate)
    monkeypatch.setattr(local_model, "missing", lambda model: "")
    return engine, calls


def test_qwen_uses_non_thinking_template_and_returns_only_completed_answer(qwen):
    engine, calls = qwen
    assert engine.translate("Hello", "vi", "en") == "Xin chào"
    assert calls[0].startswith("<|im_start|>system\n")
    assert "into Vietnamese" in calls[0]
    assert "<|im_start|>user\nHello<|im_end|>\n" in calls[0]
    assert calls[0].endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n")
    assert calls[1]["include_prompt_in_result"] is False
    assert calls[1]["return_end_token"] is True
    assert calls[1]["max_length"] == 512 and calls[1]["sampling_topk"] == 1
    count = len(calls)
    assert engine.translate("Hello", "en", "en") == "Hello"
    assert len(calls) == count


@pytest.mark.parametrize("tokens,message,target", [
    (["Xin"], "did not finish", "vi"),
    (["<|im_end|>"], "did not return", "vi"),
    (["<think>", "reason", "<|im_end|>"], "did not return", "vi"),
    (["you", "a", "give", "you"] * 16 + ["<|im_end|>"], "kept repeating", "vi"),
    (["你好", "<|im_end|>"], "instead of translating", "vi"),
    (["Hello", "<|im_end|>"], "requested language", "ja"),
])
def test_qwen_rejects_incomplete_repetitive_or_wrong_script_output(qwen, tokens, message, target):
    engine, _ = qwen
    engine._model.generate_batch = lambda *a, **kw: [SimpleNamespace(sequences=[tokens])]
    with pytest.raises(TranslateError, match=message):
        engine.translate("Hello", target, "en")


def test_qwen_input_limits_and_missing_files_can_retry_after_download(qwen, monkeypatch):
    engine, calls = qwen
    with pytest.raises(TranslateError, match="does not support"):
        engine.translate("Hello", "invalid", "en")
    with pytest.raises(TranslateError, match="too long"):
        engine.translate("word " * 1100, "vi", "en")
    assert not any(isinstance(call, dict) for call in calls)
    monkeypatch.setattr(local_model, "missing", lambda model: "download first")
    with pytest.raises(TranslateError, match="download first") as caught:
        engine.translate("Hello", "vi", "en")
    assert caught.value.wait == 0


def test_qwen_normalizes_chinese_script_for_requested_target(qwen):
    engine, _ = qwen
    engine._model.generate_batch = lambda *a, **kw: [SimpleNamespace(sequences=[["請稍等，我想進入VR。", "<|im_end|>"]])]
    assert engine.translate("Please wait, I want to enter VR.", "zh", "en") == "请稍等，我想进入VR。"
    assert engine.translate("Please wait, I want to enter VR.", "yue", "en") == "請稍等，我想進入VR。"


def test_qwen_loads_cpu_once_and_releases_other_weights(qwen, monkeypatch):
    fake, _ = qwen
    creates = []
    def create(root, **kwargs):
        creates.append((root, kwargs))
        return fake._model
    monkeypatch.setitem(sys.modules, "ctranslate2", SimpleNamespace(Generator=create))
    monkeypatch.setitem(sys.modules, "tokenizers", SimpleNamespace(
        Tokenizer=SimpleNamespace(from_file=lambda path: fake._tokenizer)))
    monkeypatch.setattr(local_inference.translator, "_model", object())
    monkeypatch.setattr(local_inference.translator, "_tokenizer", object())
    engine = local_inference.LocalQwenTranslator()
    assert engine.translate("Hello", "vi", "en") == "Xin chào"
    assert engine.translate("Hello again", "vi", "en") == "Xin chào"
    assert creates == [(str(local_model.model_folder("qwen3-1.7b-ct2")),
                        dict(device="cpu", compute_type="int8", inter_threads=1, intra_threads=2))]
    assert local_inference.translator._model is None
    assert local_inference.translator._tokenizer is None
