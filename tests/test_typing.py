"""VRChat's typing dots: shown only before the first message after 30 seconds without one,
then messages switch directly. Stand-ins for VRChat, the microphone and the speech model."""
from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from engine.speech import MIC, SPEAKER, SpeechEngine
from engine.stt import Heard, SttError
from engine.vad import FRAME, FRAME_S, RATE, Segment, Segmenter
from ui.config import Settings
from ui.live_backend import LiveBackend
from ui.backend import Utterance
from vrc.chatbox import QUIET_S, TypingDots, VRChatState
from vrc.translate import TranslateError

READY = VRChatState(running=True, pid=1, listening=True)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class Box:
    """VRChat's chatbox: remembers what it was told, in order."""

    def __init__(self, broken: bool = False):
        self.events, self.broken = [], broken

    def send(self, text, sound=False):
        self.events.append(("send", text))

    def typing(self, on):
        if self.broken:
            raise OSError("VRChat is closed")
        self.events.append(("typing", on))


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


# ---- the rule itself ----------------------------------------------------------------------

def test_dots_come_only_before_the_first_message_after_a_quiet_time():
    clock, box = Clock(), Box()
    dots = TypingDots(box, clock=clock)
    dots.starting()
    dots.starting()                                    # still talking: no second "on"
    dots.sent()
    assert box.events == [("typing", True), ("typing", False)]
    clock.now += 10
    dots.starting()                                    # the conversation goes on: no dots
    dots.sent()
    assert box.events == [("typing", True), ("typing", False)]
    clock.now += QUIET_S + 1
    dots.starting()                                    # a real pause: dots again
    assert box.events[-1] == ("typing", True)


def test_a_message_that_never_comes_turns_the_dots_off_and_the_next_one_is_still_first():
    clock, box = Clock(), Box()
    dots = TypingDots(box, clock=clock)
    dots.starting()
    dots.cancelled()
    dots.starting()
    assert box.events == [("typing", True), ("typing", False), ("typing", True)]


def test_a_closed_vrchat_does_not_break_the_dots():
    dots = TypingDots(Box(broken=True), clock=Clock())
    dots.starting()
    dots.cancelled()
    assert dots.on is False


# ---- the window's chatbox sender ----------------------------------------------------------

class Source:
    def __init__(self, target, on_audio=None):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def level(self):
        return 0.0


class Upper:
    def prepare(self):
        pass

    def translate(self, text, target, likely_source="", heard=False):
        return text.upper()


def backend(app, state=READY, **settings):
    clock, box = Clock(), Box()
    live = LiveBackend(chatbox=box, find=lambda: state, clock=clock, translator=Upper(),
                       threaded=False, game_audio=Source, mic_audio=Source)
    live.settings = Settings(**settings)
    return live, box, clock


def test_typed_text_shows_the_dots_until_its_message_arrives(app):
    live, box, _ = backend(app)
    live.send_text("xin chào")
    assert box.events == [("typing", True), ("send", "XIN CHÀO"), ("typing", False)]


def test_messages_right_after_the_first_one_switch_without_dots(app):
    live, box, clock = backend(app)
    live.send_text("one")
    clock.now += 10
    live.send_text("two")
    assert box.events[3:] == [("send", "TWO")]
    clock.now += QUIET_S + 1
    live.send_text("three")
    assert box.events[4:] == [("typing", True), ("send", "THREE"), ("typing", False)]


def test_my_voice_starts_the_dots_only_when_the_switches_allow_it(app):
    live, box, _ = backend(app, chatbox_typing=False)
    live.typing_started()
    live.apply_settings(Settings(mic_on=False))
    live.typing_started()
    assert box.events == []
    live.apply_settings(Settings())
    live.typing_started()
    live.typing_cancelled()
    assert box.events == [("typing", True), ("typing", False)]


def test_turning_the_switch_off_clears_dots_that_are_showing(app):
    live, box, _ = backend(app)
    live.typing_started()
    live.apply_settings(Settings(chatbox_typing=False))
    assert box.events == [("typing", True), ("typing", False)]


def test_vrchat_not_ready_takes_the_dots_away(app):
    live, box, _ = backend(app, state=VRChatState(running=True, pid=1, listening=False))
    live.send_text("hello")
    assert box.events == [("typing", True), ("typing", False)]      # nothing could be sent


# ---- the engine: when I start talking, and when it comes to nothing -----------------------

class LoudIsSpeech:
    def reset(self):
        pass

    def probabilities(self, samples):
        return (np.abs(samples.reshape(-1, FRAME)).mean(axis=1) > 0.1).astype("float32") * 0.9


def sound(seconds: float, loud: bool) -> np.ndarray:
    return np.full(round(seconds / FRAME_S) * FRAME, 0.5 if loud else 0.0, dtype="float32")


def test_the_sentence_cutter_reports_talking_and_talking_that_came_to_nothing():
    events, found = [], []
    cutter = Segmenter(found.append, vad=LoudIsSpeech(), on_start=lambda: events.append("start"),
                       on_drop=lambda: events.append("drop"))
    cutter.feed(np.concatenate([sound(1.0, True), sound(1.5, False)]), RATE)
    assert events == ["start"] and len(found) == 1
    cutter.feed(np.concatenate([sound(0.1, True), sound(1.5, False)]), RATE)    # a click
    assert events == ["start", "start", "drop"] and len(found) == 1


class Window:
    def __init__(self):
        self.settings = Settings(hearing="local")
        self.events = []
        self.last_heard = ""
        self.speech_status = ""
        self.on_game_audio = self.on_mic_audio = None

        class Signal:
            def emit(_self, line):
                pass
        self.utterance = Signal()

    def speech_target_lang(self):
        return "en"

    def send_to_chatbox(self, line, text=None):
        self.events.append("send")

    def typing_started(self):
        self.events.append("dots on")

    def typing_cancelled(self):
        self.events.append("dots off")


class Hears:
    def __init__(self, text="", error=None):
        self.text, self.error = text, error

    def load(self):
        pass

    def transcribe(self, samples, lang, prefer=()):
        if self.error:
            raise SttError(self.error)
        return Heard(self.text, lang or "vi")


def engine(window, hears):
    return SpeechEngine(window, engines={"local": hears, "gemini": hears}, translator=Upper(),
                        vads={MIC: LoudIsSpeech(), "speaker": LoudIsSpeech()})


def sentence():
    return Segment(np.zeros(RATE, dtype="float32"), 0.0)


def test_starting_to_talk_into_my_microphone_turns_the_dots_on():
    window = Window()
    eng = engine(window, Hears("xin chào"))
    eng._queue = lambda source, segment: None
    eng.cut(MIC, np.concatenate([sound(1.0, True), sound(1.5, False)]), RATE)
    assert window.events == ["dots on"]


@pytest.mark.parametrize("hears", [Hears(""), Hears(error="no provider key yet")])
def test_a_sentence_of_mine_that_brings_no_text_turns_the_dots_off(hears):
    window = Window()
    engine(window, hears).hear(MIC, sentence())
    assert window.events == ["dots off"]


class RoutingTranslator:
    def __init__(self):
        self.asked = []

    def translate(self, text, target, likely_source="", heard=False):
        self.asked.append((text, target, likely_source, heard))
        return f"{target}: {text}"


@pytest.mark.parametrize("mine, theirs, typed, last_heard, voice_target", [
    ("en", "vi", "zh", "zh", "vi"),       # the screenshots; a past player must not override VI
    ("en", "vi", "en", "zh", "vi"),       # sending typed English must not skip voice translation
    ("vi", "en", "zh", "vi", "en"),       # swapped voice languages
    ("en", "yue", "zh", "vi", "yue"),     # Cantonese is separate from Mandarin
    ("ja", "ko", "ja", "vi", "ko"),
    ("ko", "ja", "ko", "en", "ja"),
    ("en", "auto", "ko", "ja", "ja"),
    ("en", "auto", "zh", "vi", "vi"),     # only Auto follows the last other player
    ("en", "auto", "vi", "yue", "yue"),
    ("vi", "auto", "zh", "", "en"),       # nobody heard yet: keep the English fallback
    ("en", "en", "zh", "vi", "en"),       # voice already in its target; typing still translates
    ("en", "vi", "auto", "zh", "vi"),     # typed Auto and explicit voice can differ
])
def test_voice_and_typed_messages_use_separate_languages(
        app, mine, theirs, typed, last_heard, voice_target):
    live, box, clock = backend(app, my_lang=mine, their_lang=theirs, send_lang=typed)
    live.last_heard = last_heard
    translator = RoutingTranslator()
    live._translator = translator
    hears = Hears("hello")
    eng = SpeechEngine(live, engines={"gemini": hears, "local": hears}, translator=translator,
                       clock=clock, vads={MIC: LoudIsSpeech(), SPEAKER: LoudIsSpeech()})
    finished = []
    live.utterance.connect(lambda line: finished.append(line) if line.final else None)
    try:
        eng.hear(MIC, sentence())
        voice = finished[-1]
        assert (voice.source, voice.src_lang, voice.dst_lang, voice.sent) == (
            MIC, mine, voice_target, True)
        assert live.last_heard == last_heard
        expected_calls = [] if mine == voice_target else [("hello", voice_target, mine, True)]
        assert translator.asked == expected_calls

        clock.now += 2
        live.send_text("typed hello")
        text = finished[-1]
        typed_target = last_heard if typed == "auto" else typed
        assert (text.source, text.dst_lang, text.sent) == ("typed", typed_target, True)
        typed_calls = [] if mine == typed_target else [("typed hello", typed_target, mine, False)]
        assert translator.asked == expected_calls + typed_calls
        voice_text = "hello" if mine == voice_target else f"hello\n{voice_target}: hello"
        assert [text for event, text in box.events if event == "send"] == [
            voice_text, "typed hello" if mine == typed_target else f"{typed_target}: typed hello"]
    finally:
        live.stop()


def test_other_players_become_subtitles_in_my_language_when_typed_target_differs(app):
    live, box, clock = backend(app, my_lang="en", their_lang="vi", send_lang="zh")
    translator = RoutingTranslator()
    hears = Hears("xin chào")
    eng = SpeechEngine(live, engines={"gemini": hears, "local": hears}, translator=translator,
                       clock=clock, vads={MIC: LoudIsSpeech(), SPEAKER: LoudIsSpeech()})
    seen = []
    live.utterance.connect(seen.append)
    try:
        eng.hear(SPEAKER, Segment(np.zeros(RATE, dtype="float32"), clock.now))
        assert translator.asked == [("xin chào", "en", "vi", True)]
        assert (seen[-1].source, seen[-1].dst_lang, seen[-1].final) == (SPEAKER, "en", True)
        assert live.last_heard == "vi" and live.target_lang() == "zh"
        assert box.events == []
    finally:
        live.stop()


@pytest.mark.parametrize("enabled, own_words", [(False, True), (True, False), (True, True)])
def test_add_speaker_words_sends_both_texts_independently_of_my_words(app, enabled, own_words):
    live, box, clock = backend(app, my_lang="en", their_lang="vi", send_lang="zh", mic_on=False,
                               show_original=False, chatbox_speaker=enabled, chatbox_original=own_words)
    translator, hears = RoutingTranslator(), Hears("xin chào")
    eng = SpeechEngine(live, engines={"gemini": hears, "local": hears}, translator=translator,
                       clock=clock, vads={MIC: LoudIsSpeech(), SPEAKER: LoudIsSpeech()})
    seen = []
    live.utterance.connect(seen.append)
    try:
        eng.hear(SPEAKER, Segment(np.zeros(RATE, dtype="float32"), clock.now))
        assert translator.asked == [("xin chào", "en", "vi", True)]
        assert seen[-1].source == SPEAKER and seen[-1].final
        assert (seen[-1].original, seen[-1].translation) == ("xin chào", "en: xin chào")
        assert seen[-1].sent is (True if enabled else None)
        assert box.events == ([("send", "en: xin chào (xin chào)")] if enabled else [])
    finally:
        live.stop()


def test_add_speaker_words_keeps_the_original_when_translation_fails(app):
    class Unavailable:
        def translate(self, *args, **kwargs):
            raise TranslateError("offline")

    live, box, clock = backend(app, my_lang="en", their_lang="vi", chatbox_speaker=True)
    hears = Hears("xin chào")
    eng = SpeechEngine(live, engines={"gemini": hears, "local": hears}, translator=Unavailable(),
                       clock=clock, vads={MIC: LoudIsSpeech(), SPEAKER: LoudIsSpeech()})
    seen = []
    live.utterance.connect(seen.append)
    try:
        eng.hear(SPEAKER, Segment(np.zeros(RATE, dtype="float32"), clock.now))
        assert box.events == [("send", "xin chào")]
        assert seen[-1].sent is True and "not translated: offline" in seen[-1].note
    finally:
        live.stop()


def test_turning_off_speaker_words_drops_waiting_speakers_and_keeps_my_messages(app):
    live, box, clock = backend(app, chatbox_speaker=True, chatbox_typing=False)
    try:
        live.send_text("first")
        line = Utterance(id=100, source=SPEAKER, original="xin chào", translation="hello",
                         src_lang="vi", dst_lang="en", final=True)
        live.send_to_chatbox(line)
        live.send_text("second")
        assert box.events == [("send", "FIRST")]
        assert line.sent is None
        live.apply_settings(Settings(chatbox_speaker=False, chatbox_typing=False))
        assert all(queued.source != SPEAKER for queued, _text in live._outbox)
        clock.now += 2
        live.pump()
        assert box.events == [("send", "FIRST"), ("send", "SECOND")]
        assert not live._outbox
        # Also cover a worker result arriving after the switch was turned off.
        live.send_to_chatbox(line)
        assert not live._outbox and line.sent is None
        live.apply_settings(Settings(chatbox_speaker=True, chatbox_typing=False))
        clock.now += 2
        live.pump()
        assert box.events == [("send", "FIRST"), ("send", "SECOND")]
    finally:
        live.stop()


def test_speaker_words_wait_for_the_same_chatbox_gap_as_my_messages(app):
    live, box, clock = backend(app, chatbox_speaker=True, chatbox_typing=False)
    try:
        live.send_text("first")
        line = Utterance(id=100, source=SPEAKER, original="xin chào", translation="hello", final=True)
        live.send_to_chatbox(line)
        assert line.sent is None and box.events == [("send", "FIRST")]
        clock.now += 2
        live.pump()
        assert line.sent is True and box.events[-1] == ("send", "hello (xin chào)")
    finally:
        live.stop()


def test_speaker_words_report_osc_off_without_sending(app):
    live, box, _ = backend(app, state=VRChatState(running=True, listening=False), chatbox_speaker=True)
    try:
        line = Utterance(id=100, source=SPEAKER, original="xin chào", translation="hello", final=True)
        live.send_to_chatbox(line)
        assert box.events == [] and line.sent is False
    finally:
        live.stop()



def test_panel_languages_do_not_change_voice_or_typed_chatbox_target(app):
    live, box, clock = backend(app, my_languages=["en"], their_languages=["vi", "ja"],
                               translated_to=["en", "ja", "ko"], send_lang="ko")
    translator = RoutingTranslator()
    finished = []
    live.utterance.connect(lambda line: finished.append(line) if line.final else None)
    live._translator = translator
    hears = Hears("hello")
    eng = SpeechEngine(live, engines={"gemini": hears, "local": hears}, translator=translator,
                       clock=clock, vads={MIC: LoudIsSpeech(), SPEAKER: LoudIsSpeech()})
    try:
        eng.hear(MIC, sentence())
        assert translator.asked == [("hello", code, "en", True) for code in ("vi", "ja", "ko")]
        assert [text for event, text in box.events if event == "send"] == ["hello\nvi: hello"]
        clock.now += 2
        live.send_text("typed hello")
        assert translator.asked[-2:] == [("typed hello", code, "en", False) for code in ("ko", "ja")]
        assert [text for event, text in box.events if event == "send"][-1] == "ko: typed hello"
        assert finished[-1].panel_targets == ("en", "ja", "ko")
        assert dict(finished[-1].panel_translations) == {
            "en": "typed hello", "ja": "ja: typed hello", "ko": "ko: typed hello"}
    finally:
        live.stop()


def test_typed_partial_results_do_not_send_or_mutate_earlier_updates(app):
    live, box, clock = backend(app, my_lang="en", send_lang="vi", translated_to=["vi", "ja", "ko"])
    updates = []
    live.utterance.connect(updates.append)
    class Translator:
        def translate(self, text, target, source):
            if target != "vi":
                assert not updates[-1].final
                assert dict(updates[-1].panel_translations)["vi"] == "Xin chào"
                assert not any(event == "send" for event, _ in box.events)
            if target == "ko":
                raise TranslateError("offline")
            return {"vi": "Xin chào", "ja": "こんにちは"}[target]
    live._translator = Translator()
    try:
        live.send_text("Hello")
        first = updates[1]
        assert not first.final and first.panel_translations == (("vi", "Xin chào"),)
        assert first.note == "" and first.sent is None
        final = updates[-1]
        assert final.final and final.id == first.id
        assert dict(final.panel_translations) == {"vi": "Xin chào", "ja": "こんにちは", "ko": ""}
        assert "offline" in final.note
        assert [text for event, text in box.events if event == "send"] == ["Xin chào"]
    finally:
        live.stop()


def test_worker_delivers_first_subtitle_while_later_language_is_blocked(app):
    import threading
    from PySide6.QtTest import QTest
    from ui.log_view import LogView
    waiting, release = threading.Event(), threading.Event()
    live, box, _ = backend(app, my_lang="en", send_lang="vi", translated_to=["vi", "ja"])
    class Translator:
        def prepare(self):
            pass
        def translate(self, text, target, source):
            if target == "ja":
                waiting.set()
                assert release.wait(5), "Test must release the translator"
            return f"{target}: {text}"
    log = LogView()
    live.utterance.connect(log.add_or_update)
    live._translator = Translator()
    live._threaded = True
    live.start()
    try:
        live.send_text("Hello")
        assert waiting.wait(3)
        QTest.qWait(50)
        row = log.rows()[0]
        assert "vi: Hello" in row.translation.text() and not row.translation.isHidden()
        assert not row.utterance.final and row.translation2.isHidden()
        assert not any(event == "send" for event, _ in box.events)
        release.set()
        for _ in range(100):
            if row.utterance.final:
                break
            QTest.qWait(10)
        assert row.utterance.final and "ja: Hello" in row.translation2.text()
        assert [text for event, text in box.events if event == "send"] == ["vi: Hello"]
    finally:
        release.set()
        live.stop()
        live._worker.join(timeout=5)
        assert not live._worker.is_alive()
        log.deleteLater()
