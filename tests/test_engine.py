"""Tests for the speech engine, with stand-ins for the voice detector, the speech model,
the translators and the window: no GPU, no network, no sound device."""
from __future__ import annotations

import numpy as np
import pytest

from engine import stt, vad
from engine.speech import MIC, SPEAKER, SpeechEngine
from engine.stt import CloudHearing, Heard, SttError
from engine.translators import LIMIT_COOL_OFF_S, Chain, ServiceChain, ServiceTranslator
from engine.vad import FRAME, FRAME_S, RATE, Segment, Segmenter
from ui.config import Settings
from vrc.translate import TranslateError


from conftest import CUSTOM_URL


@pytest.fixture(autouse=True)
def models(tmp_path, monkeypatch):
    """A configured custom API; other services start without keys."""
    from engine import services
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    services.save("custom", key="k", url=CUSTOM_URL, hear_model="whisper-large-v3-turbo",
                  translate_model="model-a, model-b")
    return services


# ---- stand-ins ----------------------------------------------------------------------------

class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class LoudIsSpeech:
    """A detector that calls every loud piece speech."""

    def reset(self) -> None:
        pass

    def probabilities(self, samples: np.ndarray) -> np.ndarray:
        return (np.abs(samples.reshape(-1, FRAME)).mean(axis=1) > 0.1).astype("float32") * 0.9


def sound(seconds: float, loud: bool) -> np.ndarray:
    pieces = round(seconds / FRAME_S)
    return np.full(pieces * FRAME, 0.5 if loud else 0.0, dtype="float32")


def segmenter(found: list, **kwargs) -> Segmenter:
    return Segmenter(found.append, vad=LoudIsSpeech(), **kwargs)


# ---- cutting sound into sentences ---------------------------------------------------------

def test_a_sentence_ends_after_a_silence_and_keeps_only_a_little_of_it():
    found, clock = [], Clock()
    seg = segmenter(found, clock=clock)
    seg.feed(np.concatenate([sound(1.0, False), sound(2.0, True), sound(1.5, False)]), RATE)
    assert len(found) == 1
    seconds = len(found[0].samples) / RATE
    assert 2.0 + vad.KEEP_SILENCE_S <= seconds <= 2.0 + vad.PRE_ROLL_S + vad.KEEP_SILENCE_S + 0.1
    assert not found[0].forced


def test_speech_end_is_when_the_voice_stopped_not_when_the_silence_was_long_enough():
    found, clock = [], Clock()
    seg = segmenter(found, clock=clock)
    seg.feed(np.concatenate([sound(1.0, True), sound(1.0, False)]), RATE)
    assert found[0].speech_end == pytest.approx(clock.now - vad.SILENCE_S, abs=FRAME_S)


def test_two_sentences_with_a_pause_between_them():
    found = []
    seg = segmenter(found)
    seg.feed(np.concatenate([sound(1.0, True), sound(1.2, False), sound(1.0, True), sound(1.2, False)]), RATE)
    assert len(found) == 2


def test_a_short_breath_does_not_split_a_sentence():
    found = []
    seg = segmenter(found)
    seg.feed(np.concatenate([sound(1.0, True), sound(0.4, False), sound(1.0, True), sound(1.2, False)]), RATE)
    assert len(found) == 1


def test_a_click_is_not_a_sentence():
    found = []
    seg = segmenter(found)
    seg.feed(np.concatenate([sound(0.1, True), sound(1.5, False)]), RATE)
    assert found == []


def test_endless_talking_is_cut_to_keep_the_delay_bounded():
    found = []
    seg = segmenter(found)
    seg.feed(sound(vad.MAX_S + 2.0, True), RATE)
    assert len(found) == 1 and found[0].forced
    assert len(found[0].samples) / RATE == pytest.approx(vad.MAX_S, abs=0.1)


def test_small_pieces_like_live_capture_give_the_same_sentence():
    whole, pieces = [], []
    stream = np.concatenate([sound(1.0, True), sound(1.5, False)])
    segmenter(whole).feed(stream, RATE)
    seg = segmenter(pieces)
    for start in range(0, len(stream), 160):          # 10 ms at a time
        seg.feed(stream[start:start + 160], RATE)
    assert len(pieces) == 1 and len(pieces[0].samples) == len(whole[0].samples)


def test_game_sound_at_48_khz_is_brought_down_to_16_khz():
    found = []
    seg = segmenter(found)
    loud = np.full(48000 * 2, 0.5, dtype="float32")
    seg.feed(np.concatenate([loud, np.zeros(48000 * 2, dtype="float32")]), 48000)
    assert len(found) == 1
    assert len(found[0].samples) / RATE == pytest.approx(2.0 + vad.KEEP_SILENCE_S, abs=0.4)


def test_detector_off_cuts_by_the_clock_and_skips_quiet_pieces():
    found = []
    seg = segmenter(found, vad_on=False)
    seg.feed(sound(vad.CLOCK_S, True), RATE)
    seg.feed(sound(vad.CLOCK_S, False), RATE)
    assert len(found) == 1 and found[0].forced


def test_switching_the_detector_drops_the_half_heard_sentence():
    found = []
    seg = segmenter(found)
    seg.feed(sound(1.0, True), RATE)
    seg.configure(vad_on=False, threshold=0.7)
    seg.feed(sound(1.0, False), RATE)
    assert found == []


# ---- speech to text ------------------------------------------------------------------------

class Answer:
    def __init__(self, status=200, body=None, headers=None, text=""):
        self.status_code, self._body, self.headers, self.text = status, body or {}, headers or {}, text

    def json(self):
        return self._body


class Http:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.answers.pop(0)

    get = post


def test_cloud_hearing_reports_the_language_as_a_code_and_writes_simplified_chinese():
    http = Http(Answer(body={"text": " 聯合國 ", "language": "Chinese"}))
    heard = CloudHearing("custom", http=http).transcribe(np.zeros(RATE, dtype="float32"), None)
    assert heard == Heard("联合国", "zh")
    assert "language" not in http.calls[0][1]["data"]


def test_cloud_hearing_knows_cantonese_and_keeps_its_traditional_characters():
    http = Http(Answer(body={"text": "佢哋係邊度嚟㗎", "language": "Cantonese"}))
    heard = CloudHearing("custom", http=http).transcribe(np.zeros(RATE, dtype="float32"), None)
    assert heard == Heard("佢哋係邊度嚟㗎", "yue")


def test_cloud_hearing_chinese_means_mandarin_or_cantonese():
    quiet = np.zeros(RATE, dtype="float32")
    http = Http(Answer(body={"text": "你食咗飯未", "language": "cantonese"}))
    assert CloudHearing("custom", http=http).transcribe(quiet, "zh").lang == "yue"
    assert "language" not in http.calls[0][1]["data"]           # asked without forcing Mandarin
    http = Http(Answer(body={"text": "knee how", "language": "english"}),
                Answer(body={"text": "你好", "language": "chinese"}))
    assert CloudHearing("custom", http=http).transcribe(quiet, "zh") == Heard("你好", "zh")
    assert http.calls[1][1]["data"]["language"] == "zh"         # heard as something else: insist


def test_cantonese_is_translated_and_answered_in_cantonese():
    clock, window = Clock(), Window(my_lang="en", their_lang="yue")
    hears = Hears("你食咗飯未", "yue")
    engine(window, hears, Fixed("Have you eaten yet?"), clock).hear(SPEAKER, sentence(clock))
    final = window.utterance.seen[-1]
    assert hears.asked == ["yue"]             # "They speak: Cantonese" is passed to the model
    assert (final.src_lang, final.dst_lang, final.translation) == ("yue", "en", "Have you eaten yet?")
    assert window.last_heard == "yue"


def test_mandarin_is_shown_simplified_and_cantonese_the_hong_kong_way():
    assert stt.tidy("聯合國還希望", "zh") == Heard("联合国还希望", "zh")
    assert stt.tidy("你吃了饭未呀", "yue") == Heard("你吃了飯未呀", "yue")
    assert stt.tidy("hello", "en") == Heard("hello", "en")


def test_words_only_cantonese_writes_mark_the_speaker_as_cantonese():
    heard = stt.tidy("我唔識講普通話,你識唔識聽廣東話?", "zh")       # the model said "Chinese"
    assert heard.lang == "yue" and "唔識" in heard.text
    assert stt.tidy("我不会说普通话", "zh").lang == "zh"
    assert not stt.looks_cantonese("佢")                           # one stray character is not enough


def test_cantonese_can_be_a_translation_target():
    from vrc.translate import chat_messages
    system = chat_messages("hello", "yue", "en")[0]["content"]
    assert "Cantonese" in system and "Traditional" in system


def test_cloud_hearing_passes_a_known_language_and_keeps_it():
    http = Http(Answer(body={"text": "xin chào", "language": "vietnamese"}))
    heard = CloudHearing("custom", http=http).transcribe(np.zeros(RATE, dtype="float32"), "vi")
    assert heard.lang == "vi" and http.calls[0][1]["data"]["language"] == "vi"


def test_cloud_hearing_waits_out_a_limit_without_asking_again():
    clock = Clock()
    http = Http(Answer(status=429, headers={"retry-after": "30"}), Answer(body={"text": "hi", "language": "english"}))
    engine = CloudHearing("custom", http=http, clock=clock)
    with pytest.raises(SttError, match="limit"):
        engine.transcribe(np.zeros(RATE, dtype="float32"), None)
    with pytest.raises(SttError, match="limit"):
        engine.transcribe(np.zeros(RATE, dtype="float32"), None)
    assert len(http.calls) == 1
    clock.now += 31
    assert engine.transcribe(np.zeros(RATE, dtype="float32"), None).text == "hi"


def test_cloud_hearing_without_a_key_says_so(models):
    with pytest.raises(SttError, match="no OpenAI key yet"):
        CloudHearing("openai", http=Http()).transcribe(np.zeros(RATE, dtype="float32"), None)
    models.save("custom", url="")
    with pytest.raises(SttError, match="Custom domain has no address yet"):
        CloudHearing("custom", http=Http()).transcribe(np.zeros(RATE, dtype="float32"), None)


def test_cloud_hearing_sends_the_sound_to_the_chosen_address_with_its_key(models):
    http = Http(Answer(body={"text": "hi", "language": "english"}))
    CloudHearing("custom", http=http).transcribe(np.zeros(RATE, dtype="float32"), "en")
    url, sent = http.calls[0]
    assert url == f"{CUSTOM_URL}/audio/transcriptions" and sent["headers"]["Authorization"] == "Bearer k"
    assert sent["data"]["response_format"] == "verbose_json"
    assert sent["data"]["model"] == "whisper-large-v3-turbo"   # from saved settings
    models.save("openai", key="sk-1", hear_model="gpt-4o-mini-transcribe")
    http = Http(Answer(body={"text": "xin chào các bạn"}))      # no language in the answer
    heard = CloudHearing("openai", http=http).transcribe(np.zeros(RATE, dtype="float32"), None)
    url, sent = http.calls[0]
    assert url == "https://api.openai.com/v1/audio/transcriptions" and sent["data"]["response_format"] == "json"
    assert heard == Heard("xin chào các bạn", "vi")             # told by its writing


def test_qwen_hearing_sends_the_sound_in_a_chat_and_reads_the_language_it_found(models):
    models.save("qwen", key="q")
    http = Http(Answer(body={"choices": [{"message": {
        "content": "你食咗飯未呀", "annotations": [{"type": "audio_info", "language": "yue"}]}}]}))
    heard = CloudHearing("qwen", http=http).transcribe(np.zeros(RATE, dtype="float32"), None)
    assert heard == Heard("你食咗飯未呀", "yue")
    url, sent = http.calls[0]
    assert url.endswith("/compatible-mode/v1/chat/completions")
    audio = sent["json"]["messages"][0]["content"][0]["input_audio"]["data"]
    assert audio.startswith("data:audio/wav;base64,UklGR")       # "RIFF": a wav file
    assert "language" not in sent["json"]["asr_options"]


def test_gemini_hearing_reads_its_json_answer_and_believes_a_language_in_its_own_script(models):
    models.save("gemini", key="g")
    http = Http(Answer(body={"choices": [{"message": {
        "content": '```json\n{"language": "ko", "text": "안녕하세요"}\n```'}}]}))
    heard = CloudHearing("gemini", http=http).transcribe(np.zeros(RATE, dtype="float32"), None)
    assert heard == Heard("안녕하세요", "ko") and len(http.calls) == 1   # no certainty: no second opinion
    sent = http.calls[0][1]["json"]
    assert sent["messages"][1]["content"][1]["input_audio"]["format"] == "wav"
    assert sent["reasoning_effort"] == "low"


def test_a_model_that_refuses_the_extra_fields_is_asked_plainly_from_then_on(models):
    models.save("gemini", key="g")
    ok = {"choices": [{"message": {"content": '{"language": "en", "text": "hello"}'}}]}
    http = Http(Answer(status=400), Answer(body=ok), Answer(body=ok))
    hearing = CloudHearing("gemini", http=http)
    assert hearing.transcribe(np.zeros(RATE, dtype="float32"), "en").text == "hello"
    assert hearing.transcribe(np.zeros(RATE, dtype="float32"), "en").text == "hello"
    assert ["reasoning_effort" in call[1]["json"] for call in http.calls] == [True, False, False]


def test_the_language_can_be_told_from_the_writing():
    guess = stt.guess_language
    assert (guess("你好吗"), guess("佢哋食咗飯未呀"), guess("こんにちは世界")) == ("zh", "yue", "ja")
    assert (guess("안녕하세요"), guess("Привет"), guess("Tôi không biết")) == ("ko", "ru", "vi")
    assert (guess("hello there"), guess("...")) == ("en", "")
    assert stt.language_code("Cantonese", "") == "yue" and stt.language_code("ZH", "") == "zh"


def test_wav_bytes_is_16_khz_mono_16_bit():
    data = stt.wav_bytes(np.zeros(RATE, dtype="float32"))
    assert data[:4] == b"RIFF" and len(data) == 44 + RATE * 2


# ---- translators ---------------------------------------------------------------------------

class Fixed:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.calls = answer, error, 0

    def prepare(self) -> None:
        pass

    def translate(self, text, target, likely_source="", heard=False):
        self.calls += 1
        self.heard = heard
        if self.error:
            raise TranslateError(self.error)
        return self.answer


def test_chain_uses_the_first_translator_that_answers():
    first, second = Fixed(error="today's free requests are used up"), Fixed("xin chào")
    chain = Chain([("a", first), ("b", second)])
    assert chain.translate("hello", "vi") == "xin chào" and chain.last_used == "b"


def test_the_chain_follows_the_service_picked_in_settings(models, tmp_path, monkeypatch):
    from engine import translators
    monkeypatch.setattr(translators, "addon_folder", lambda: tmp_path / "no such folder")
    picked = ["custom"]
    chain = ServiceChain(lambda: picked[0])
    assert chain.names() == ["custom:model-a", "custom:model-b"]   # saved models, in order
    models.save("openrouter", key="o", translate_model="qwen/qwen3-32b, xiaomi/mimo-v2.6-flash")
    picked[0] = "openrouter"
    assert chain.names() == ["openrouter:qwen/qwen3-32b", "openrouter:xiaomi/mimo-v2.6-flash"]
    picked[0] = "mimo"
    assert chain.names() == ["mimo:mimo-v2-flash"]           # the service's default model
    with pytest.raises(TranslateError, match="no Xiaomi MiMo key yet"):
        chain.translate("x", "vi")
    models.save("custom", url="http://127.0.0.1:8000/v1", key="c", translate_model="")
    picked[0] = "custom"
    with pytest.raises(TranslateError, match="no translating model yet"):
        chain.translate("x", "vi")


def test_a_translator_rests_as_long_as_the_service_says(models):
    clock = Clock()
    busy = Answer(status=429, headers={"retry-after": "30"}, body={"error": {"message": "busy"}})
    http = Http(busy, Answer(body={"choices": [{"message": {"content": "ok"}}]}))
    chain = Chain([("custom", ServiceTranslator("custom", "model-a", http=http))], clock=clock)
    with pytest.raises(TranslateError, match="Custom domain: busy"):
        chain.translate("x", "vi")
    clock.now += 31
    assert chain.translate("x", "vi") == "ok"


def test_a_model_that_answers_in_chinese_instead_of_translating_lets_the_next_one_answer(models):
    said = lambda text: Answer(body={"choices": [{"message": {"content": text}}]})
    first = Http(said("今天天气真好"), said("Hôm nay trời đẹp"))
    second = Http(said("Hôm nay thời tiết đẹp"))
    chain = Chain([("a", ServiceTranslator("custom", "model-a", http=first)),
                   ("b", ServiceTranslator("custom", "model-b", http=second))])
    assert chain.translate("今天天气很好", "vi", "zh", heard=True) == "Hôm nay thời tiết đẹp"
    assert chain.translate("今天天气很好", "vi", "zh", heard=True) == "Hôm nay trời đẹp"   # not rested
    assert stt.mostly_chinese("今天天气真好") and not stt.mostly_chinese("Hôm nay, 你好 friend")


def test_a_missing_key_is_asked_about_again_at_once(models):
    chain = Chain([("openai", ServiceTranslator("openai", "m", http=Http()))])
    with pytest.raises(TranslateError, match="no OpenAI key yet"):
        chain.translate("x", "vi")
    with pytest.raises(TranslateError, match="no OpenAI key yet"):   # not "resting": checked again
        chain.translate("x", "vi")


def test_services_keep_keys_and_fall_back_to_their_defaults(models):
    assert models.setting("openai", "url") == "https://api.openai.com/v1"
    assert models.setting("openai", "hear_model") == "whisper-1" and not models.ready("openai")
    models.save("openai", key=" sk-1 ", hear_model="whisper-1")
    assert models.ready("openai") and models.setting("openai", "key") == "sk-1"
    models.save("openai", hear_model="")                      # empty: back to the default
    import json
    saved = json.loads(models.models_file().read_text(encoding="utf-8"))
    assert saved["openai"] == {"key": "sk-1"} and saved["custom"]["key"] == "k"
    assert models.setting("custom", "url") == CUSTOM_URL                # from saved settings


def test_a_refused_request_is_explained_in_plain_words(models):
    assert models.failure("custom", Answer(status=401)).startswith("Custom domain did not accept the key (Settings → Models)")
    limit = Answer(status=429, body={"error": {"message": "Rate limit reached in organization org_123"}})
    assert models.failure("custom", limit) == "Custom domain: Rate limit reached in organization org_123"
    assert models.failure("openai", Answer(status=500, body={"error": {"message": "oops"}})) == "OpenAI error 500: oops"


def test_the_set_up_window_can_test_a_key(models):
    http = Http(Answer(body={"data": []}))
    assert models.check("custom", http=http) == (True, "the key works")
    assert http.calls[0][0] == f"{CUSTOM_URL}/models"
    ok, text = models.check("openai", key="sk-bad", http=Http(Answer(status=401)))
    assert not ok and "did not accept the key" in text
    http = Http(Answer(body={"data": {}}))
    assert models.check("openrouter", key="o", http=http)[0] and http.calls[0][0].endswith("/api/v1/key")
    models.save("custom", url="")
    assert models.check("custom", key="c") == (False, "no address yet")


def test_a_pc_s_own_add_on_translators_are_fallback(models, tmp_path, monkeypatch):
    from engine import translators
    (tmp_path / "mine.py").write_text(
        "class Mine:\n"
        "    def prepare(self): pass\n"
        "    def translate(self, text, target, likely_source='', heard=False): return 'from mine'\n"
        "def translators(): return [('mine', Mine())]\n", encoding="utf-8")
    (tmp_path / "broken.py").write_text("this is not python", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")
    monkeypatch.setattr(translators, "addon_folder", lambda: tmp_path)
    calls = []
    def unavailable(self, *args, **kwargs):
        calls.append(self.model)
        raise TranslateError("unavailable")
    monkeypatch.setattr(ServiceTranslator, "translate", unavailable)
    chain = ServiceChain(lambda: "custom")
    assert chain.names() == ["custom:model-a", "custom:model-b", "mine"]
    assert chain.translate("hello", "vi") == "from mine" and chain.last_used == "mine"
    assert calls == ["model-a", "model-b"]


def test_selected_custom_model_takes_priority_over_gemini_addon(models, monkeypatch):
    models.save("custom", translate_model="qwen/qwen3.8-27b")
    addon = Fixed("from gemini")
    calls = []
    def translate(self, *args, **kwargs):
        calls.append((self.service, self.model))
        return "from selected model"
    monkeypatch.setattr(ServiceTranslator, "translate", translate)
    chain = ServiceChain(lambda: "custom", addons=[("gemini", addon)])
    assert chain.translate("hello", "vi") == "from selected model"
    assert calls == [("custom", "qwen/qwen3.8-27b")]
    assert addon.calls == 0
    assert chain.last_used == "custom:qwen/qwen3.8-27b"


@pytest.mark.parametrize("model, runtime", [
    ("nllb-200-ct2", "translator"), ("qwen3-1.7b-ct2", "qwen_translator")])
def test_local_failure_never_calls_addons_and_keeps_the_local_error(models, monkeypatch, model, runtime):
    from engine import local_inference, local_model
    local_model.select(model)
    local = Fixed("local answer")
    addon = Fixed(error="Gemini can't be reached (no internet?)")
    monkeypatch.setattr(local_inference, runtime, local)
    clock = Clock()
    chain = ServiceChain(lambda: "local", addons=[("gemini", addon)], clock=clock)
    assert chain.translate("hello", "zh", "en") == "local answer"
    local.error = "Local model could not translate this sentence"
    for target in ("vi", "zh"):
        with pytest.raises(TranslateError, match="^Local model could not translate this sentence$"):
            chain.translate("hello", target, "en", heard=True)
    assert local.calls == 2  # The second failure preserves the error during cooldown.
    assert addon.calls == 0
    local.error = None
    clock.now += 61
    assert chain.translate("hello", "vi", "en") == "local answer"
    assert chain.names() == [f"local:{model}"]
    assert chain.last_used == f"local:{model}"


def test_addons_load_only_for_online_service_and_stay_out_of_local_chain(models, monkeypatch):
    from engine import translators, local_inference
    loaded = []
    addon = Fixed("addon answer")
    def load():
        loaded.append(True)
        return [("gemini", addon)]
    monkeypatch.setattr(translators, "addon_translators", load)
    monkeypatch.setattr(local_inference, "translator", Fixed("local answer"))
    def offline(*args, **kwargs):
        raise TranslateError("offline")
    monkeypatch.setattr(ServiceTranslator, "translate", offline)
    selected = ["local"]
    chain = ServiceChain(lambda: selected[0])
    chain.prepare()
    assert chain.translate("hello", "vi", "en") == "local answer"
    assert loaded == []
    selected[0] = "custom"
    assert chain.translate("hello", "vi", "en") == "addon answer"
    assert loaded == [True] and addon.calls == 1
    selected[0] = "local"
    assert chain.translate("hello", "vi", "en") == "local answer"
    assert chain.names() == ["local:nllb-200-ct2"]
    assert addon.calls == 1


def test_chain_skips_a_translator_that_hit_its_limit_until_it_rested():
    clock = Clock()
    first, second = Fixed(error="the service's limit was reached"), Fixed("ok")
    chain = Chain([("a", first), ("b", second)], clock=clock)
    chain.translate("x", "vi")
    chain.translate("x", "vi")
    assert first.calls == 1
    clock.now += LIMIT_COOL_OFF_S + 1
    chain.translate("x", "vi")
    assert first.calls == 2


def test_chain_gives_the_last_reason_when_nobody_answers():
    chain = Chain([("a", Fixed(error="no internet")), ("b", Fixed(error="no provider key yet"))])
    with pytest.raises(TranslateError, match="no provider key yet"):
        chain.translate("x", "vi")


def test_service_translator_sends_the_chat_prompt_and_cleans_the_answer():
    http = Http(Answer(body={"choices": [{"message": {"content": " 你好\n吗 "}}]}))
    assert ServiceTranslator("custom", "qwen/qwen3.8-27b", http=http).translate("xin chào", "zh", "vi") == "你好 吗"
    body = http.calls[0][1]["json"]
    assert body["model"] == "qwen/qwen3.8-27b" and "Simplified Chinese" in body["messages"][0]["content"]
    assert "reasoning_effort" not in body


def test_service_translator_limit_and_empty_answers_are_translate_errors():
    with pytest.raises(TranslateError, match="limit"):
        ServiceTranslator("custom", "m", http=Http(Answer(status=429))).translate("x", "vi")
    with pytest.raises(TranslateError, match="empty"):
        ServiceTranslator("custom", "m", http=Http(Answer(body={"choices": [{"message": {"content": ""}}]}))).translate("x", "vi")


# ---- the whole engine ----------------------------------------------------------------------

class Signal:
    def __init__(self):
        self.seen = []

    def emit(self, line) -> None:
        self.seen.append(line)


class Window:
    """What the engine needs from ui.live_backend.LiveBackend."""

    def __init__(self, **settings):
        self.settings = Settings(**{"hearing": "local", **settings})
        self.utterance = Signal()
        self.last_heard = ""
        self.speech_status = ""
        self.sent = []
        self.on_game_audio = self.on_mic_audio = None

    def speech_target_lang(self) -> str:
        return self.settings.chatbox_languages(self.last_heard)[0]

    def send_to_chatbox(self, line, text=None) -> None:
        self.sent.append(line)


class Hears:
    def __init__(self, text="你好", lang="zh", error=None):
        self.text, self.lang, self.error, self.asked = text, lang, error, []

    def load(self) -> None:
        pass

    def transcribe(self, samples, lang, prefer=()):
        self.asked.append(lang)
        self.prefer = prefer
        if self.error:
            raise SttError(self.error)
        return Heard(self.text, lang or self.lang)


def engine(window, hears, translator=None, clock=None) -> SpeechEngine:
    return SpeechEngine(window, engines={"local": hears, "custom": Hears("from the service", "en")},
                        translator=translator or Fixed("xin chào"), clock=clock or Clock(),
                        vads={SPEAKER: LoudIsSpeech(), MIC: LoudIsSpeech()})


def sentence(clock, ago=0.5) -> Segment:
    return Segment(np.zeros(RATE, dtype="float32"), clock.now - ago)


def test_another_player_is_shown_first_as_heard_then_translated_into_my_language():
    clock, window = Clock(), Window(my_lang="vi")
    engine(window, Hears("你好", "zh"), clock=clock).hear(SPEAKER, sentence(clock))
    first, final = window.utterance.seen
    assert (first.final, first.original, first.translation) == (False, "你好", "")
    assert (final.final, final.id, final.translation) == (True, first.id, "xin chào")
    assert (final.source, final.src_lang, final.dst_lang, final.latency_ms) == ("speaker", "zh", "vi", 500)
    assert first.id >= 1_000_000 and window.last_heard == "zh" and window.sent == []


def test_spoken_lines_tell_the_translator_that_words_may_be_misheard():
    clock, window, translator = Clock(), Window(my_lang="vi"), Fixed("xin chào")
    engine(window, Hears("你好", "zh"), translator, clock).hear(SPEAKER, sentence(clock))
    assert translator.heard is True


def test_service_translator_adds_the_misheard_note_only_for_spoken_lines():
    answer = {"choices": [{"message": {"content": "ok"}}]}
    http = Http(Answer(body=answer), Answer(body=answer))
    chat = ServiceTranslator("custom", "m", http=http)
    chat.translate("x", "vi", heard=True)
    chat.translate("x", "vi")
    spoken, typed = (call[1]["json"]["messages"][0]["content"] for call in http.calls)
    assert "speech recognition" in spoken and "speech recognition" not in typed


def test_another_player_already_in_my_language_is_not_translated():
    clock, window, translator = Clock(), Window(my_lang="vi"), Fixed("never")
    engine(window, Hears("xin chào", "vi"), translator, clock).hear(SPEAKER, sentence(clock))
    final = window.utterance.seen[-1]
    assert translator.calls == 0 and final.translation == "" and final.dst_lang == "vi"


def test_their_language_is_detected_on_auto_and_given_when_picked():
    clock = Clock()
    for their, expected in (("auto", None), ("zh", "zh")):
        hears = Hears()
        engine(Window(their_lang=their), hears, clock=clock).hear(SPEAKER, sentence(clock))
        assert hears.asked == [expected]


def test_my_voice_is_heard_in_my_language_and_goes_to_the_chatbox_not_the_window():
    clock, window = Clock(), Window(my_lang="vi")
    window.last_heard = "zh"
    hears = Hears("xin chào", "vi")
    engine(window, hears, Fixed("你好"), clock).hear(MIC, sentence(clock))
    assert hears.asked == ["vi"]
    assert [line.final for line in window.utterance.seen] == [False]
    sent = window.sent[0]
    assert (sent.source, sent.final, sent.translation, sent.dst_lang) == ("mic", True, "你好", "zh")
    assert window.last_heard == "zh"          # my own voice never changes "the language heard last"


def test_a_failed_translation_keeps_the_heard_text_and_says_why():
    clock, window = Clock(), Window(my_lang="vi")
    engine(window, Hears("hello", "en"), Fixed(error="no internet"), clock).hear(SPEAKER, sentence(clock))
    final = window.utterance.seen[-1]
    assert final.translation == "" and final.dst_lang == "en" and final.note == "not translated: no internet"


def test_the_same_line_twice_in_a_row_is_music_fooling_the_model():
    clock, window = Clock(), Window()
    eng = engine(window, Hears("Thank you.", "en"), clock=clock)
    eng.hear(SPEAKER, sentence(clock))
    eng.hear(SPEAKER, sentence(clock))
    assert len([line for line in window.utterance.seen if line.final]) == 1
    clock.now += 60
    eng.hear(SPEAKER, sentence(clock))
    assert len([line for line in window.utterance.seen if line.final]) == 2


def test_an_old_sentence_from_another_player_is_dropped_but_mine_never_is():
    clock, window = Clock(), Window()
    eng = engine(window, Hears("hello", "en"), clock=clock)
    eng.hear(SPEAKER, sentence(clock, ago=30))
    assert window.utterance.seen == []
    eng.hear(MIC, sentence(clock, ago=30))
    assert len(window.sent) == 1


def test_nothing_heard_shows_nothing_and_a_problem_becomes_the_status():
    clock, window = Clock(), Window()
    engine(window, Hears("", "en"), clock=clock).hear(SPEAKER, sentence(clock))
    assert window.utterance.seen == [] and window.speech_status == "Listening"
    engine(window, Hears(error="the service's limit was reached"), clock=clock).hear(SPEAKER, sentence(clock))
    assert window.speech_status == "the service's limit was reached"


def test_the_hearing_engine_follows_the_setting():
    clock, window = Clock(), Window(hearing="custom")
    engine(window, Hears("local", "en"), clock=clock).hear(SPEAKER, sentence(clock))
    assert window.utterance.seen[0].original == "from the service"


def test_an_online_service_is_made_when_it_is_first_picked():
    window = Window(hearing="qwen")
    eng = SpeechEngine(window, engines={"local": Hears()}, translator=Fixed("x"), clock=Clock())
    assert eng._engine() is eng._engines["local"]             # no Qwen key: this PC stands in
    assert isinstance(eng._engines["qwen"], CloudHearing) and eng._missing.startswith("no Qwen")


def test_cloud_hearing_without_a_key_falls_back_to_hearing_on_this_pc():
    clock, window = Clock(), Window(hearing="openai")
    no_key = CloudHearing("openai", http=Http())
    eng = SpeechEngine(window, engines={"local": Hears("local", "en"), "openai": no_key},
                       translator=Fixed("x"), clock=clock)
    eng.hear(SPEAKER, sentence(clock))
    assert window.utterance.seen[0].original == "local"


def test_no_key_and_no_local_model_names_both_reasons():
    clock, window = Clock(), Window(hearing="openai")
    eng = SpeechEngine(window, engines={"local": Hears(error="the speech model could not be loaded"),
                                        "openai": CloudHearing("openai", http=Http())},
                       translator=Fixed("x"), clock=clock)
    eng.hear(SPEAKER, sentence(clock))
    assert window.speech_status == ("no OpenAI key yet (Settings → Models), "
                                    "and the speech model could not be loaded")


def test_custom_domain_hears_and_translates_by_default():
    assert (Settings().hearing, Settings().translating) == ("custom", "custom")


def test_the_microphone_has_its_own_strictness_setting():
    clock, window = Clock(), Window(vad_sensitivity=0.3, mic_vad_sensitivity=0.95)
    eng = engine(window, Hears(), clock=clock)
    heard = []
    eng._queue = lambda source, segment: heard.append(source)
    stream = np.concatenate([sound(1.0, True), sound(1.5, False)])
    eng.cut(MIC, stream, RATE)                # 0.9 from the stand-in is under 0.95: not speech
    assert heard == []
    eng.cut(SPEAKER, stream, RATE)
    assert heard == [SPEAKER]


def test_live_sound_runs_through_the_detector_with_the_window_s_strictness():
    clock, window = Clock(), Window(vad_sensitivity=0.95)
    eng = engine(window, Hears(), clock=clock)
    heard = []
    eng.hear = lambda source, segment: heard.append(source)
    eng._queue = lambda source, segment: heard.append(source)
    stream = np.concatenate([sound(1.0, True), sound(1.5, False)])
    eng.cut(SPEAKER, stream, RATE)            # 0.9 from the stand-in is under 0.95: not speech
    assert heard == []
    eng.cut(MIC, stream, RATE)                # the mic keeps its own, lower threshold
    assert heard == [MIC]


# ---- what the downloadable program leaves out ----------------------------------------------

def test_the_voice_detector_brings_its_own_model_file():
    assert vad.MODEL_FILE.exists()
    detector = vad.SileroVad()
    quiet = detector.probabilities(np.zeros(FRAME * 4, dtype="float32"))
    assert quiet.shape == (4,) and float(quiet.max()) < 0.5


def test_without_the_local_model_this_pc_hearing_says_what_to_do(monkeypatch):
    monkeypatch.setattr(stt.local_model, "installed", lambda model=None: False)
    with pytest.raises(SttError, match="choose an online service"):
        stt.LocalWhisper().load()


def test_before_its_download_the_local_model_says_where_to_get_it(monkeypatch):
    monkeypatch.setattr(stt.local_model, "installed", lambda model=None: True)
    monkeypatch.setattr(stt.local_model, "nvidia_card", lambda: True)
    monkeypatch.setattr(stt.local_model, "gpu_folders", lambda: [])
    with pytest.raises(SttError, match="not downloaded yet"):
        stt.LocalWhisper().load()


def test_the_local_model_loads_from_the_program_s_own_download(monkeypatch, tmp_path):
    made = []

    class Model:
        def __init__(self, source, **options):
            made.append((source, options))

        def transcribe(self, samples, **options):
            return [], None
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(stt.local_model, "missing", lambda model=None: "")
    monkeypatch.setattr(stt.local_model, "ready", lambda root=None, model=None: True)
    monkeypatch.setattr(stt.local_model, "gpu_folders", lambda: [])
    monkeypatch.setattr(stt, "whisper_class", lambda: Model)
    stt.LocalWhisper().load()
    assert made == [(str(tmp_path / "VRChat-Translator" / "local-model" / "whisper"),
                     {"device": "cuda", "compute_type": "float16"})]


# ---- on Auto, focus on our languages -------------------------------------------------------

def whisper_answer(text, language, certainty):
    import math
    return Answer(body={"text": text, "language": language,
                        "segments": [{"avg_logprob": math.log(certainty)}]})


def test_cloud_hearing_believes_another_language_only_when_sure_and_in_its_own_script():
    quiet = np.zeros(RATE, dtype="float32")
    http = Http(whisper_answer("안녕하세요 반갑습니다", "Korean", 0.9))
    assert CloudHearing("custom", http=http).transcribe(quiet, None) == Heard("안녕하세요 반갑습니다", "ko")
    assert len(http.calls) == 1
    http = Http(whisper_answer("Hola, ¿qué tal estás hoy?", "Spanish", 0.85))
    assert CloudHearing("custom", http=http).transcribe(quiet, None).lang == "es"


def test_cloud_hearing_unsure_of_another_language_takes_the_main_language_that_fits_best():
    quiet = np.zeros(RATE, dtype="float32")
    http = Http(whisper_answer("Te tomé de ahí, ¿no?", "Spanish", 0.45),      # the guess: not sure
                whisper_answer("the tome day, no?", "english", 0.40),         # asked again as English
                whisper_answer("他从那儿来的，对吧", "chinese", 0.70),            # ... as Chinese: best
                whisper_answer("tê tô mê đây nô", "vietnamese", 0.30),
                whisper_answer("こんにちは", "japanese", 0.20), whisper_answer("안녕", "korean", 0.20))
    heard = CloudHearing("custom", http=http).transcribe(quiet, None, prefer=("en",))
    assert heard == Heard("他从那儿来的，对吧", "zh")
    assert [call[1]["data"].get("language") for call in http.calls] == [None, "en", "zh", "vi", "ja", "ko"]


def test_cloud_hearing_asks_first_in_the_language_heard_last_and_stops_when_sure():
    quiet = np.zeros(RATE, dtype="float32")
    http = Http(whisper_answer("Привет", "Russian", 0.5), whisper_answer("你好啊", "chinese", 0.9))
    heard = CloudHearing("custom", http=http).transcribe(quiet, None, prefer=("yue", "en"))
    assert heard.lang == "zh" and len(http.calls) == 2      # Cantonese is asked as Chinese


def test_cloud_hearing_wrong_script_is_never_believed():
    quiet = np.zeros(RATE, dtype="float32")
    http = Http(whisper_answer("thank you very much", "Korean", 0.95), whisper_answer("thank you very much", "english", 0.95))
    assert CloudHearing("custom", http=http).transcribe(quiet, None).lang == "en"
    assert stt.in_own_script("ありがとう", "ja") and not stt.in_own_script("arigato", "ja")
    assert stt.in_own_script("anything", "es")


class FakeWhisper:
    """Stands in for faster-whisper's model: one scripted (text, language, probability) per call."""

    def __init__(self, *runs):
        self.runs, self.asked = list(runs), []

    def transcribe(self, samples, language=None, **options):
        from types import SimpleNamespace
        self.asked.append(language)
        text, lang, probability = self.runs.pop(0)
        segment = SimpleNamespace(text=text, no_speech_prob=0.0, avg_logprob=-0.1, compression_ratio=1.0)
        info = SimpleNamespace(language=language or lang, language_probability=probability,
                               all_language_probs=[("es", 0.7), ("zh", 0.2), ("en", 0.05)])
        return [segment], info


def test_local_whisper_under_80_percent_sure_takes_our_most_likely_language():
    local = stt.LocalWhisper()
    local._model = FakeWhisper(("te tomé de ahí", "es", 0.7), ("他从那儿来的", "zh", 1.0))
    assert local.transcribe(np.zeros(RATE, dtype="float32"), None) == Heard("他从那儿来的", "zh")
    assert local._model.asked == [None, "zh"]


def test_local_whisper_at_80_percent_or_more_keeps_the_other_language():
    local = stt.LocalWhisper()
    local._model = FakeWhisper(("hola a todos", "es", 0.85))
    assert local.transcribe(np.zeros(RATE, dtype="float32"), None) == Heard("hola a todos", "es")


@pytest.mark.parametrize("code, text", [("ja", "今日は何をしますか？"), ("ko", "오늘 뭐 해요?")])
def test_japanese_and_korean_auto_detection_and_explicit_language(code, text):
    quiet = np.zeros(RATE, dtype="float32")
    for hint in (None, code):
        http = Http(whisper_answer(text, code, 0.6))
        assert CloudHearing("custom", http=http).transcribe(quiet, hint) == Heard(text, code)
        assert len(http.calls) == 1
        assert http.calls[0][1]["data"].get("language") == hint
        local = stt.LocalWhisper()
        local._model = FakeWhisper((text, code, 0.6))
        assert local.transcribe(quiet, hint) == Heard(text, code)
        assert local._model.asked == [hint]
    assert stt.in_own_script(text, code)
    assert stt.in_own_script("東京駅", "ja")


@pytest.mark.parametrize("code, text", [("ja", "こんにちは"), ("ko", "안녕하세요")])
@pytest.mark.parametrize("send_chatbox", [False, True])
def test_japanese_and_korean_speakers_translate_and_update_auto_target(code, text, send_chatbox):
    clock, window, translator = Clock(), Window(my_lang="en", chatbox_speaker=send_chatbox), Fixed("Hello")
    engine(window, Hears(text, code), translator, clock).hear(SPEAKER, sentence(clock))
    final = window.sent[-1] if send_chatbox else window.utterance.seen[-1]
    assert (final.original, final.translation, final.src_lang, final.dst_lang) == (text, "Hello", code, "en")
    assert window.last_heard == code and translator.calls == 1
    assert bool(window.sent) == send_chatbox


@pytest.mark.parametrize("code, name, text", [("ja", "Japanese", "こんにちは"), ("ko", "Korean", "안녕하세요")])
def test_translation_request_supports_japanese_and_korean_targets(code, name, text):
    http = Http(Answer(body={"choices": [{"message": {"content": text}}]}))
    result = ServiceTranslator("custom", "model-a", http=http).translate("hello", code, "en")
    assert result == text
    assert "into " + name in http.calls[0][1]["json"]["messages"][0]["content"]


def test_another_language_is_announced_not_translated():
    clock, window, translator = Clock(), Window(my_lang="en", chatbox_speaker=True), Fixed("never")
    window.last_heard = "zh"
    eng = engine(window, Hears("Привет", "ru"), translator, clock)
    eng.hear(SPEAKER, sentence(clock))
    (line,) = window.utterance.seen
    assert (line.final, line.source, line.src_lang, line.original, line.translation) == (True, "speaker", "ru", "", "")
    assert translator.calls == 0 and window.last_heard == "zh" and window.sent == []
    eng.hear(SPEAKER, sentence(clock))                    # still Russian: not said again at once
    assert len(window.utterance.seen) == 1
    clock.now += 60
    eng.hear(SPEAKER, sentence(clock))
    assert len(window.utterance.seen) == 2


def test_the_hearing_engine_is_told_which_of_our_languages_to_try_first():
    clock, window = Clock(), Window(my_lang="vi")
    window.last_heard = "zh"
    hears = Hears("hello", "en")
    engine(window, hears, clock=clock).hear(SPEAKER, sentence(clock))
    assert hears.prefer == ("zh", "vi")


def test_cloud_hearing_under_80_percent_still_believes_a_language_that_beats_all_of_ours():
    quiet = np.zeros(RATE, dtype="float32")
    http = Http(whisper_answer("Что ты делаешь?", "Russian", 0.62), whisper_answer("今天干什么", "chinese", 0.33),
                whisper_answer("oh no more hugger", "english", 0.35), whisper_answer("ô nô mô ha gô", "vietnamese", 0.5),
                whisper_answer("こんにちは", "japanese", 0.20), whisper_answer("안녕", "korean", 0.20))
    assert CloudHearing("custom", http=http).transcribe(quiet, None, prefer=("zh",)).lang == "ru"


def test_cloud_hearing_made_up_sign_off_lines_never_win():
    quiet = np.zeros(RATE, dtype="float32")
    http = Http(whisper_answer("Привет, приятно познакомиться.", "Russian", 0.62), whisper_answer("你好", "chinese", 0.3),
                whisper_answer("on your say oh", "english", 0.35),
                whisper_answer("Hãy subscribe cho kênh Ghiền Mì Gõ Để không bỏ lỡ những video hấp dẫn", "vietnamese", 0.9),
                whisper_answer("こんにちは", "japanese", 0.20), whisper_answer("안녕", "korean", 0.20))
    assert CloudHearing("custom", http=http).transcribe(quiet, None).lang == "ru"
    assert stt.tidy("Thanks for watching!", "en") == Heard("", "en")
    assert stt.tidy("Thank you.", "en") == Heard("Thank you.", "en")       # people do say this


def test_cloud_hearing_a_language_believed_lately_is_not_asked_about_again():
    quiet, clock = np.zeros(RATE, dtype="float32"), Clock()
    http = Http(whisper_answer("Привет всем", "Russian", 0.9), whisper_answer("Что делаешь", "Russian", 0.55),
                whisper_answer("Хорошо", "Russian", 0.55), whisper_answer("okay", "english", 0.2),
                whisper_answer("好的", "chinese", 0.7), whisper_answer("ô kê", "vietnamese", 0.2),
                whisper_answer("こんにちは", "japanese", 0.20), whisper_answer("안녕", "korean", 0.20))
    engine_ = CloudHearing("custom", http=http, clock=clock)
    assert engine_.transcribe(quiet, None).lang == "ru"
    assert engine_.transcribe(quiet, None).lang == "ru" and len(http.calls) == 2    # no second opinion
    clock.now += 120
    assert engine_.transcribe(quiet, None).lang == "zh" and len(http.calls) == 8    # a minute later: checked again


from engine import services


def test_fetch_models_returns_sorted_list_of_ids():
    http = Http(Answer(body={"data": [{"id": "whisper-1"}, {"id": "gpt-4o"}]}))
    assert services.fetch_models("custom", url="http://127.0.0.1:8000/v1", key="c", http=http) == ["gpt-4o", "whisper-1"]
    assert http.calls[0][0] == "http://127.0.0.1:8000/v1/models"
    assert http.calls[0][1]["headers"]["Authorization"] == "Bearer c"


def test_fetch_models_handles_ollama_and_list_formats():
    http1 = Http(Answer(body={"models": [{"name": "qwen2.5:7b"}, {"name": "llama3.2:3b"}]}))
    assert services.fetch_models("custom", url="http://127.0.0.1:11434", key="", http=http1) == ["llama3.2:3b", "qwen2.5:7b"]
    http2 = Http(Answer(body=["model-b", "model-a"]))
    assert services.fetch_models("custom", url="http://127.0.0.1:8000/v1", http=http2) == ["model-a", "model-b"]


def test_fetch_models_falls_back_to_v1_if_404():
    http = Http(Answer(status=404), Answer(body={"data": [{"id": "model-1"}]}))
    assert services.fetch_models("custom", url="http://127.0.0.1:8000", http=http) == ["model-1"]
    assert http.calls[0][0] == "http://127.0.0.1:8000/models"
    assert http.calls[1][0] == "http://127.0.0.1:8000/v1/models"


def test_fetch_models_error_handling():
    http = Http(Answer(status=401, body={"error": {"message": "Invalid key"}}))
    with pytest.raises(OSError, match="Custom domain did not accept the key"):
        services.fetch_models("custom", url="http://127.0.0.1:8000/v1", key="bad", http=http)
    services.save("custom", url="")
    assert services.fetch_models("custom", url="", key="") == []


def test_speech_engine_auto_switches_hearing_to_local_when_cloud_unavailable():
    clock, window = Clock(), Window(hearing="openai")
    switched = []
    window.setting_switched = type("Sig", (), {"emit": lambda s, k, v: switched.append((k, v))})()
    eng = SpeechEngine(window, engines={"local": Hears("local", "en"), "openai": CloudHearing("openai", http=Http())},
                       translator=Fixed("x"), clock=clock)
    eng.hear(SPEAKER, sentence(clock))
    assert window.utterance.seen[0].original == "local"
    assert ("hearing", "local") in switched
    assert window.settings.hearing == "local"


def test_chain_notifies_on_switch_when_model_is_used():
    switched = []
    first, second = Fixed(error="limit"), Fixed("ok")
    chain = Chain([("a:m1", first), ("a:m2", second)], on_switch=lambda name: switched.append(name))
    assert chain.translate("hello", "vi") == "ok"
    assert switched == ["a:m2"]



def test_microphone_translates_three_panel_targets_and_keeps_partial_success():
    class Translator:
        def __init__(self, failed=""):
            self.calls = []
            self.failed = failed
        def translate(self, text, target, source, heard=False):
            self.calls.append((target, heard))
            if target == self.failed:
                raise TranslateError("offline")
            return {"vi": "Xin chào", "ja": "こんにちは", "ko": "안녕하세요"}[target]
    for failed in ("", "vi", "ja", "ko"):
        clock, window = Clock(), Window(my_lang="en", their_lang="vi", translated_to=["vi", "ja", "ko"])
        window.speech_target_lang = lambda: "vi"
        translator = Translator(failed)
        engine(window, Hears("Hello", "en"), translator, clock).hear(MIC, sentence(clock))
        line = window.sent[0]
        assert translator.calls == [("vi", True), ("ja", True), ("ko", True)]
        assert line.translation == ("" if failed == "vi" else "Xin chào")
        assert dict(line.panel_translations) == {
            code: "" if code == failed else text
            for code, text in (("vi", "Xin chào"), ("ja", "こんにちは"), ("ko", "안녕하세요"))}
        assert ("offline" in line.note) == bool(failed)


def test_panel_targets_are_captured_before_settings_change():
    class Pending:
        def submit(self, function, *args):
            self.function, self.args = function, args
    clock, window = Clock(), Window(my_lang="en", their_lang="vi", translated_to=["en", "ja", "ko"])
    window.speech_target_lang = lambda: "vi"
    speech = engine(window, Hears("Hello", "en"), clock=clock)
    pending = Pending()
    speech._mic_pool = pending
    speech.hear(MIC, sentence(clock))
    window.settings.translated_to = ["zh"]
    pending.function(*pending.args)
    assert window.sent[0].panel_targets == ("en", "ja", "ko")
    assert dict(window.sent[0].panel_translations)["en"] == "Hello"


def test_microphone_captures_all_chatbox_targets_and_reuses_panel_results():
    class Pending:
        def submit(self, function, *args):
            self.function, self.args = function, args
    class Translator:
        def __init__(self):
            self.calls = []
        def translate(self, text, target, source, heard=False):
            self.calls.append((target, heard))
            return f"{target}: {text}"
    clock, window = Clock(), Window(my_languages=["en"], their_languages=["zh", "vi", "en"],
                                    translated_to=["en", "zh", "vi"])
    translator = Translator()
    speech = engine(window, Hears("Hello", "en"), translator, clock)
    speech._mic_pool = pending = Pending()
    speech.hear(MIC, sentence(clock))
    window.settings.their_languages = ["ja"]
    window.settings.translated_to = ["ko"]
    pending.function(*pending.args)
    assert translator.calls == [("zh", True), ("vi", True)]
    line = window.sent[0]
    assert line.chatbox_targets == ("zh", "vi", "en")
    assert dict(line.chatbox_translations) == {"zh": "zh: Hello", "vi": "vi: Hello", "en": "Hello"}
    assert dict(line.panel_translations) == dict(line.chatbox_translations)


@pytest.mark.parametrize("source", [MIC, SPEAKER])
@pytest.mark.parametrize("failed", ["", "ja", "ko"])
def test_panel_results_arrive_before_later_translations_without_extra_sends(source, failed):
    clock, window = Clock(), Window(my_lang="en", translated_to=["vi", "ja", "ko"])
    window.speech_target_lang = lambda: "vi"
    class Translator:
        def translate(self, text, target, source, heard=False):
            assert heard
            if target in ("ja", "ko"):
                partial = window.utterance.seen[-1]
                assert not partial.final
                assert dict(partial.panel_translations)["vi"] == "vi: Hello"
                assert window.sent == []
            if target == failed:
                raise TranslateError("offline")
            return f"{target}: {text}"
    engine(window, Hears("Hello", "en"), Translator(), clock).hear(source, sentence(clock))
    partial = window.utterance.seen[1]
    assert partial.panel_translations == (("vi", "vi: Hello"),) and not partial.final
    assert window.utterance.seen[0].panel_translations == ()
    final = window.sent[0] if source == MIC else window.utterance.seen[-1]
    assert final.final and final.id == partial.id
    assert dict(final.panel_translations) == {
        code: "" if code == failed else f"{code}: Hello" for code in ("vi", "ja", "ko")}
    assert ("offline" in final.note) == bool(failed)
    assert len(window.sent) == (1 if source == MIC else 0)


def test_auto_resolving_to_second_target_does_not_translate_twice():
    clock, window, translator = Clock(), Window(my_lang="en", their_lang2="ja"), Fixed("こんにちは")
    window.last_heard = "ja"
    engine(window, Hears("Hello", "en"), translator, clock).hear(MIC, sentence(clock))
    assert translator.calls == 1
    assert window.sent[0].dst_lang2 == ""


def test_two_their_languages_allow_detection_and_prefer_both():
    clock, hears = Clock(), Hears("こんにちは", "ja")
    window = Window(my_lang="en", their_lang="vi", their_lang2="ja")
    engine(window, hears, clock=clock).hear(SPEAKER, sentence(clock))
    assert hears.asked == [None]
    assert hears.prefer[:2] == ("vi", "ja")
    assert window.utterance.seen[-1].dst_lang == "en"
    assert not window.utterance.seen[-1].dst_lang2


@pytest.mark.parametrize("source", [MIC, SPEAKER])
@pytest.mark.parametrize("heard_lang,accepted", [("ja", True), ("ko", False)])
def test_multiple_source_languages_detect_and_filter(source, heard_lang, accepted):
    clock, hears = Clock(), Hears("こんにちは", heard_lang)
    window = Window(my_languages=["en", "zh", "ja"], their_languages=["en", "zh", "ja"],
                    translated_to=["vi", "en", "zh"])
    engine(window, hears, clock=clock).hear(source, sentence(clock))
    assert hears.asked == [None]
    assert hears.prefer == ("en", "zh", "ja")
    assert bool(window.utterance.seen) == accepted
    if accepted:
        assert window.utterance.seen[0].panel_targets == ("vi", "en", "zh")


def test_saved_model_change_is_seen_even_when_file_stamp_is_unchanged(models):
    import os
    models.save("custom", translate_model="model-a")
    assert models.setting("custom", "translate_model") == "model-a"
    path = models.models_file()
    before = path.stat()
    models.save("custom", translate_model="model-b")
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert path.stat().st_size == before.st_size
    assert models.setting("custom", "translate_model") == "model-b"


def test_cooldown_keeps_the_original_error_without_retrying():
    clock = Clock()
    translator = Fixed(error="Custom domain error 404: endpoint not found")
    chain = Chain([("custom:chat", translator)], clock=clock)
    for _ in range(2):
        with pytest.raises(TranslateError, match="Custom domain error 404: endpoint not found"):
            chain.translate("hello", "vi")
    assert translator.calls == 1


@pytest.mark.parametrize("field,value", [("url", "https://fixed.test/v1"), ("key", "replacement-key")])
def test_changing_api_credentials_clears_translation_cooldown(models, monkeypatch, field, value):
    clock = Clock()
    models.save("custom", translate_model="chat")
    calls = []
    def translate(self, *a, **kw):
        calls.append(True)
        if len(calls) == 1:
            raise TranslateError("endpoint or key rejected")
        return "xin chào"
    monkeypatch.setattr(ServiceTranslator, "translate", translate)
    chain = ServiceChain(lambda: "custom", clock=clock, addons=[])
    for _ in range(2):
        with pytest.raises(TranslateError, match="endpoint or key rejected"):
            chain.translate("hello", "vi")
    assert len(calls) == 1
    models.save("custom", **{field: value})
    assert chain.translate("hello", "vi") == "xin chào"
    assert len(calls) == 2


def test_custom_404_is_not_reported_as_a_working_connection(models):
    ok, message = models.check("custom", http=Http(Answer(status=404, body={"error": "endpoint missing"})))
    assert not ok
    assert "404" in message and "check the API base address" in message


@pytest.mark.parametrize("source,expected", [("vi", "vi"), ("", "zh")])
def test_nllb_custom_model_uses_direct_translation_api(source, expected):
    http = Http(Answer(body={"translated_text": " hello\nworld "}))
    translator = ServiceTranslator("custom", "nllb-200-ct2", http=http)
    assert translator.translate("你好", "en", source) == "hello world"
    url, request = http.calls[0]
    assert url == CUSTOM_URL + "/translate"
    assert request["json"] == {"text": "你好", "source_language": expected, "target_language": "en"}
    assert request["headers"]["Authorization"] == "Bearer k"


@pytest.mark.parametrize("answer", [Answer(status=429), Answer(body={"translated_text": ""}),
                                  Answer(body={"wrong": "shape"}), Answer(body={"translated_text": 12})])
def test_nllb_errors_follow_normal_translation_fallback(answer):
    with pytest.raises(TranslateError):
        ServiceTranslator("custom", "nllb-200-ct2", http=Http(answer)).translate("hello", "vi", "en")
