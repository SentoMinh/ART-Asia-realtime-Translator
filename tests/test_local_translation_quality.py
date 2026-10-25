"""Local NLLB keeps sentences and retries only clearly runaway output."""
from types import SimpleNamespace

import pytest

from engine import local_inference, local_model
from vrc.translate import TranslateError


@pytest.mark.parametrize("text,expected", [
    ("Can you wait a bit? I want to move to VR first.",
     ["Can you wait a bit?", "I want to move to VR first."]),
    ("你好。等一下！我先喝水。", ["你好。", "等一下！", "我先喝水。"]),
    ('「待って！」次に行く。', ['「待って！」', '次に行く。']),
    ('He said "Wait!" Then left.', ['He said "Wait!"', 'Then left.']),
    ("Dr. Smith uses 3.14 at example.com. Next sentence.",
     ["Dr. Smith uses 3.14 at example.com.", "Next sentence."]),
    ("Mr. A. Smith lives in the U.S. today.", ["Mr. A. Smith lives in the U.S. today."]),
    ("Well... maybe later.", ["Well... maybe later."]),
    ("Go! Go! Go!", ["Go!", "Go!", "Go!"]),
    ("  One sentence without punctuation  ", ["One sentence without punctuation"]),
    ("   ", []),
])
def test_sentence_boundaries(text, expected):
    assert local_inference.translation_sentences(text) == expected


@pytest.fixture
def fake_translator(monkeypatch):
    translator = local_inference.LocalTranslator()
    translator._tokenizer = SimpleNamespace(
        encode=lambda text, **kwargs: SimpleNamespace(tokens=text.split()),
        token_to_id=lambda token: token,
        decode=lambda tokens, **kwargs: " ".join(t for t in tokens if t != "</s>"))
    monkeypatch.setattr(local_model, "missing", lambda *args: "")
    return translator


def result(*tokens):
    return SimpleNamespace(hypotheses=[["zho_Hans", *tokens, "</s>"]])


def test_nllb_translates_foreign_words_inside_source_language_output(fake_translator):
    calls = []
    def translate(tokens, **kwargs):
        calls.append(tokens)
        return [result("Yes,", "do", "you", "know", "how", "to?")]
    fake_translator._model = SimpleNamespace(translate_batch=translate)
    assert fake_translator.translate("对 do you know how to.", "en", "en") == "Yes, do you know how to?"
    assert calls == [[["eng_Latn", "对", "do", "you", "know", "how", "to.", "</s>"]]]


def test_all_sentences_keep_their_order_and_target_prefix(fake_translator):
    def translate(tokens, **kwargs):
        assert tokens == [["eng_Latn", "Wait?", "</s>"], ["eng_Latn", "Move", "to", "VR.", "</s>"]]
        assert kwargs == {"target_prefix": [["zho_Hans"], ["zho_Hans"]], "beam_size": 1}
        return [result("等一下？"), result("我想先去VR。")]
    fake_translator._model = SimpleNamespace(translate_batch=translate)
    assert fake_translator.translate("Wait? Move to VR.", "zh", "en") == "等一下？ 我想先去VR。"


@pytest.mark.parametrize("bad_results", [[result("等一下？"), result()], [result("等一下？")]])
def test_missing_sentence_is_an_error_instead_of_partial_success(fake_translator, bad_results):
    fake_translator._model = SimpleNamespace(translate_batch=lambda *args, **kwargs: bad_results)
    with pytest.raises(TranslateError, match="sentence"):
        fake_translator.translate("Wait? Move to VR.", "zh", "en")


@pytest.mark.parametrize("retry_fails", [False, True])
def test_runaway_sentence_retries_once_without_repeating_good_sentences(fake_translator, retry_fails, caplog):
    loop = result(*(["you", "give", "you", "a"] * 30))
    calls = []
    def translate(tokens, **kwargs):
        calls.append((tokens, kwargs))
        if len(calls) == 1:
            return [loop, result("Good sentence.")]
        assert len(calls) == 2
        assert tokens == [["eng_Latn", "Stutter.", "</s>"]]
        assert kwargs["no_repeat_ngram_size"] == 4
        return [loop if retry_fails else result("Recovered sentence.")]
    fake_translator._model = SimpleNamespace(translate_batch=translate)
    if retry_fails:
        with pytest.raises(TranslateError, match="kept repeating"):
            fake_translator.translate("Stutter. Next.", "zh", "en")
    else:
        assert fake_translator.translate("Stutter. Next.", "zh", "en") == "Recovered sentence. Good sentence."
    assert len(calls) == 2
    assert "repetition detected" in caplog.text


def test_normal_repetition_does_not_retry_or_remove_words(fake_translator):
    phrase = "go " * 50
    calls = []
    def translate(tokens, **kwargs):
        calls.append(kwargs)
        return [result(*(["走"] * 50))]
    fake_translator._model = SimpleNamespace(translate_batch=translate)
    assert fake_translator.translate(phrase, "zh", "en").split() == ["走"] * 50
    assert calls == [{"target_prefix": [["zho_Hans"]], "beam_size": 1}]
