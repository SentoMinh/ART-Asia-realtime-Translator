import os
import socket
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import time

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from ui.config import Settings
from ui.live_backend import LiveBackend
from vrc.translate import NoTranslator, TranslateError, chat_messages
from vrc import chatbox
from vrc.chatbox import MAX_CHARS, MIN_GAP_S, Chatbox, VRChatState, encode_message, fit, fit_bilingual


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


# ---- OSC bytes --------------------------------------------------------------

def test_chatbox_message_bytes():
    assert encode_message("/chatbox/input", "hi", True, False) == (
        b"/chatbox/input\0\0" + b",sTF\0\0\0\0" + b"hi\0\0")


def test_strings_are_utf8_and_padded_to_four():
    message = encode_message("/chatbox/input", "你好", True, False)
    assert len(message) % 4 == 0
    assert message.endswith("你好".encode("utf-8") + b"\0\0")       # 6 bytes + 2 zeros
    assert encode_message("/a", "abcd").endswith(b"abcd\0\0\0\0")   # a full block still ends in zeros


def test_typing_and_numbers():
    assert encode_message("/chatbox/typing", True) == b"/chatbox/typing\0" + b",T\0\0"
    assert encode_message("/x", 1, 0.5).endswith(struct.pack(">i", 1) + struct.pack(">f", 0.5))
    with pytest.raises(TypeError):
        encode_message("/x", None)


def test_fit_cuts_long_text_and_tidies_spaces():
    assert fit("  a \n b  ") == ("a b", False)
    text, cut = fit("x" * 300)
    assert cut and len(text) == MAX_CHARS and text.endswith("…")
    assert fit("x" * MAX_CHARS) == ("x" * MAX_CHARS, False)


@pytest.mark.parametrize("translation, original, expected", [
    (" hello ", "xin\nchào", "hello (xin chào)"),
    ("", "xin chào", "xin chào"),
    ("hello", "hello", "hello"),
])
def test_bilingual_chatbox_includes_both_texts_without_duplicates(translation, original, expected):
    assert fit_bilingual(translation, original) == (expected, False)


@pytest.mark.parametrize("translation, original", [
    ("x" * 200, "y" * 200), ("你好", "y" * 300), ("x" * 300, "xin chào"),
])
def test_long_speaker_messages_keep_room_for_translation_and_original(translation, original):
    outgoing, cut = fit_bilingual(translation, original)
    assert cut and len(outgoing) <= MAX_CHARS and outgoing.endswith(")")
    translated_part, original_part = outgoing[:-1].split(" (", 1)
    for full, shortened in ((translation, translated_part), (original, original_part)):
        assert len(shortened) >= min(len(full), 60)
        if len(full) < 60:
            assert shortened == full
        else:
            assert shortened.endswith("…") and full.startswith(shortened[:-1])


def test_packet_really_arrives():
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(2)
    box = Chatbox(port=receiver.getsockname()[1])
    box.send("xin chào")
    data, _ = receiver.recvfrom(1024)
    box.close()
    receiver.close()
    assert data == encode_message("/chatbox/input", "xin chào", True, False)


# ---- finding VRChat ---------------------------------------------------------

def test_udp_table_parsing():
    rows = [(0, socket.htons(9000), 111), (0, socket.htons(5353), 222), (0, socket.htons(9000), 333)]
    raw = struct.pack("<I", len(rows)) + b"".join(struct.pack("<III", *row) for row in rows)
    assert chatbox.parse_udp_table(raw, 9000) == {111, 333}
    assert chatbox.parse_udp_table(struct.pack("<I", 0), 9000) == set()


def test_find_vrchat_states(monkeypatch):
    monkeypatch.setattr(chatbox, "process_ids", lambda: [])
    assert chatbox.find_vrchat() == VRChatState()
    monkeypatch.setattr(chatbox, "process_ids", lambda: [42])
    monkeypatch.setattr(chatbox, "udp_port_owners", lambda port: {7})
    assert chatbox.find_vrchat() == VRChatState(running=True, pid=42, listening=False)
    monkeypatch.setattr(chatbox, "udp_port_owners", lambda port: {42})
    assert chatbox.find_vrchat().ready


def test_process_list_works_on_this_pc():
    assert chatbox.process_ids("python.exe") or chatbox.process_ids("pythonw.exe")
    assert isinstance(chatbox.udp_port_owners(9000), set)


# ---- translating ------------------------------------------------------------

def test_prompt_names_the_languages():
    system = chat_messages("xin chào", "zh", "vi")[0]["content"]
    assert "into Simplified Chinese" in system and "most likely in Vietnamese" in system
    assert "most likely" not in chat_messages("hi", "en", "en")[0]["content"]
    assert chat_messages("xin chào", "zh")[1] == {"role": "user", "content": "xin chào"}
    assert "speech recognition" not in system
    assert "speech recognition" in chat_messages("xin chào", "zh", "vi", heard=True)[0]["content"]


def test_without_an_engine_typed_text_is_not_translated_and_says_why():
    with pytest.raises(TranslateError, match="no translator is installed"):
        NoTranslator().translate("xin chào", "zh", "vi")
    NoTranslator().prepare()


# ---- the backend ------------------------------------------------------------

class FakeChatbox:
    def __init__(self):
        self.sent = []

    def send(self, text, sound=False):
        self.sent.append(text)


class FakeTranslator:
    """Upper-cases instead of translating; `error` makes it fail like a used-up daily limit."""

    def __init__(self):
        self.asked = []
        self.error = ""

    def prepare(self):
        pass

    def translate(self, text, target, likely_source=""):
        self.asked.append((text, target, likely_source))
        if self.error:
            raise TranslateError(self.error)
        return text.upper()


READY = VRChatState(running=True, pid=1, listening=True)


class FakeSource:
    """Stands in for GameAudio / MicAudio, so tests never open real sound devices."""
    made = []

    def __init__(self, target, on_audio=None):
        if target == "broken mic":
            raise RuntimeError("device unplugged")
        self.target, self.on_audio, self.running, self.loud = target, on_audio, False, 0.0
        FakeSource.made.append(self)

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def level(self):
        return self.loud


def make(app, state, threaded=False):
    now = [100.0]
    box = FakeChatbox()
    FakeSource.made = []
    backend = LiveBackend(chatbox=box, find=lambda: state, clock=lambda: now[0],
                          translator=FakeTranslator(), threaded=threaded,
                          game_audio=FakeSource, mic_audio=FakeSource)
    seen, statuses = [], []
    backend.utterance.connect(lambda u: seen.append((u.id, u.sent, u.note, u.original)))
    backend.status_changed.connect(statuses.append)
    return backend, box, now, seen, statuses


def test_status_follows_vrchat(app):
    for state, level in ((VRChatState(), "error"), (VRChatState(running=True), "warn"),
                         (VRChatState(running=True, listening=True), "ok")):
        backend, _, _, _, statuses = make(app, state)
        backend.poll()
        assert statuses[-1].level == level


def test_text_is_sent_when_vrchat_listens(app):
    backend, box, _, seen, _ = make(app, VRChatState(running=True, pid=1, listening=True))
    lines = []
    backend.utterance.connect(lambda u: lines.append((u.final, u.translation, u.src_lang, u.dst_lang)))
    backend.send_text("  hello   there ")
    assert box.sent == ["HELLO THERE"]                      # the translation, not the typed text
    assert lines[0] == (False, "", "vi", "en")              # first shown as "translating…"
    assert lines[-1][:2] == (True, "HELLO THERE")
    assert seen[-1][1] is True and seen[-1][2] == ""
    assert backend._translator.asked == [("hello there", "en", "vi")]


def test_target_language_follows_they_speak(app):
    backend, box, _, _, _ = make(app, READY)
    backend.apply_settings(Settings(send_lang="zh"))
    backend.last_heard = "vi"
    backend.send_text("a")
    assert backend.target_lang() == "zh"                     # picked next to Send: always that one
    assert backend._translator.asked[0][1] == "zh"
    backend.apply_settings(Settings(send_lang="auto", their_lang="zh"))
    assert backend.target_lang() == "vi"                     # auto: the language heard last from audio
    backend.last_heard = ""
    assert backend.target_lang() == "zh"                     # nobody heard yet: "They speak"
    backend.apply_settings(Settings())
    assert backend.target_lang() == "en"                     # everything on auto


def test_failed_translation_sends_the_typed_text_and_says_why(app):
    backend, box, _, seen, _ = make(app, READY)
    backend._translator.error = "today's free requests are used up"
    backend.send_text("xin chào")
    assert box.sent == ["xin chào"]
    assert seen[-1][1] is True and "not translated: today's free requests" in seen[-1][2]


def test_chatbox_can_carry_my_own_words_and_long_text_is_cut(app):
    backend, box, _, seen, _ = make(app, READY)
    backend.apply_settings(Settings(chatbox_original=True))
    backend.send_text("xin chào")
    assert box.sent == ["XIN CHÀO (xin chào)"]
    backend.apply_settings(Settings())
    backend._last_sent = -100
    backend.send_text("x" * 300)
    assert len(box.sent[-1]) == MAX_CHARS and "cut to 144" in seen[-1][2]


def test_worker_thread_round_trip(app):
    backend, box, _, seen, _ = make(app, READY, threaded=True)
    backend.start()
    backend.send_text("hello")
    deadline = time.monotonic() + 3
    while not box.sent and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    backend.stop()
    assert box.sent == ["HELLO"] and seen[-1][1] is True


def test_nothing_is_sent_without_vrchat(app):
    backend, box, _, seen, _ = make(app, VRChatState())
    backend.send_text("hello")
    assert box.sent == [] and seen[-1][1] is False
    backend, box, _, seen, _ = make(app, VRChatState(running=True))
    backend.send_text("hello")
    assert box.sent == [] and seen[-1][1] is False
    backend.send_text("   ")
    assert len(seen) == 2                # "translating…" and the result of the one real line


def test_messages_keep_the_gap(app):
    backend, box, now, seen, _ = make(app, VRChatState(running=True, pid=1, listening=True))
    backend.send_text("one")
    backend.send_text("two")
    backend.send_text("three")
    assert box.sent == ["ONE"] and seen[-1][1] is None   # translated, waiting for its turn
    backend.pump()                       # too early: nothing goes out
    assert box.sent == ["ONE"]
    now[0] += MIN_GAP_S
    backend.pump()
    assert box.sent == ["ONE", "TWO"]
    now[0] += MIN_GAP_S
    backend.pump()
    assert box.sent == ["ONE", "TWO", "THREE"] and seen[-1][1] is True
    backend.stop()


# ---- sound ------------------------------------------------------------------

def test_level_scale():
    from vrc.audio import stereo_to_mono, to_level
    assert to_level(np.zeros(480, dtype=np.float32)) == 0.0
    assert to_level(np.array([], dtype=np.float32)) == 0.0
    assert to_level(np.ones(480, dtype=np.float32)) == 1.0
    assert 0.4 < to_level(np.full(480, 0.02, dtype=np.float32)) < 0.5      # normal speech
    assert to_level(np.full(480, 0.0005, dtype=np.float32)) == 0.0          # under the floor
    stereo = np.array([1.0, 0.0, 0.5, 0.5, 9.0], dtype=np.float32).tobytes()   # a cut-off last frame
    assert stereo_to_mono(stereo).tolist() == [0.5, 0.5]


def test_game_sound_follows_vrchat_and_the_switch(app):
    state = VRChatState(running=True, pid=7, listening=True)
    backend, _, _, _, statuses = make(app, state)
    backend.poll()
    game = backend._game
    assert game.running and game.target == 7 and backend._mic.running
    assert statuses[-1].level == "ok" and "sound is being captured" in statuses[-1].detail
    backend.poll()
    assert backend._game is game                      # not restarted on every check
    state.pid = 8                                     # VRChat was restarted
    backend.poll()
    assert not game.running and backend._game.target == 8
    backend.apply_settings(Settings(subtitles_on=False, mic_on=False))
    backend.poll()
    assert backend._game is None and backend._mic is None
    assert all(not source.running for source in FakeSource.made)
    state.running = False
    backend.apply_settings(Settings())
    backend.poll()
    assert backend._game is None and statuses[-1].level == "error"


def test_levels_and_audio_reach_the_window_and_the_engine(app):
    backend, _, _, _, _ = make(app, READY)
    backend.poll()
    levels, chunks = {}, []
    backend.speaker_level.connect(lambda v: levels.__setitem__("game", v))
    backend.mic_level.connect(lambda v: levels.__setitem__("mic", v))
    backend._game.loud, backend._mic.loud = 0.7, 0.25
    backend._emit_levels()
    assert levels == {"game": 0.7, "mic": 0.25}
    backend.on_game_audio = lambda mono, rate: chunks.append(("game", rate))
    backend._game.on_audio(np.zeros(4, dtype=np.float32), 48000)
    backend._mic.on_audio(np.zeros(4, dtype=np.float32), 44100)        # no mic listener: ignored
    assert chunks == [("game", 48000)]


def test_sound_problems_are_shown_not_hidden(app):
    backend, _, _, _, statuses = make(app, READY)
    backend.apply_settings(Settings(mic_device="broken mic"))
    backend.poll()
    assert backend._mic is None and backend._game is not None
    assert statuses[-1].level == "ok"
    assert "Your microphone is not captured: device unplugged" in statuses[-1].detail
    backend._game_factory = None                       # the audio packages are missing
    backend._stop_source("_game")
    backend.poll()
    assert statuses[-1].level == "warn" and statuses[-1].text == "No game sound"
    assert "not captured: the audio packages are not installed" in statuses[-1].detail
    backend.apply_settings(Settings(mic_device=""))    # picking a working microphone recovers
    backend.poll()
    assert backend._mic is not None and backend._mic.running


def test_spoken_line_from_the_engine_goes_to_the_chatbox(app):
    from ui.backend import Utterance
    backend, box, _, seen, _ = make(app, READY)
    line = Utterance(id=1_000_001, source="mic", original="xin chào", translation="hello",
                     src_lang="vi", dst_lang="en", final=True, latency_ms=900)
    backend.send_to_chatbox(line)
    assert box.sent == ["xin chào\nhello"] and seen[-1][:2] == (1_000_001, True)
    untranslated = Utterance(id=1_000_002, source="mic", original="ừ", final=True,
                             note="not translated: limit reached")
    backend._last_sent = -100
    backend.send_to_chatbox(untranslated)
    assert box.sent[-1] == "ừ" and seen[-1][2] == "not translated: limit reached"


def test_send_failure_is_reported(app):
    backend, box, _, seen, _ = make(app, VRChatState(running=True, pid=1, listening=True))

    def broken(text, sound=False):
        raise OSError("network down")
    box.send = broken
    backend.send_text("hello")
    assert seen[-1][1] is False and "could not send" in seen[-1][2]



def test_three_language_lines_reach_osc_in_one_message(app):
    from ui.backend import Utterance
    backend, box, _, _, _ = make(app, READY)
    backend.send_to_chatbox(Utterance(
        id=42, source="mic", original="Hello", translation="Xin chào",
        translation2="こんにちは", src_lang="en", dst_lang="vi", dst_lang2="ja", final=True))
    assert box.sent == ["Hello\nXin chào\nこんにちは"]
    assert "Hello\nXin chào\nこんにちは".encode() in encode_message("/chatbox/input", box.sent[0], True, False)


def test_long_multilingual_output_keeps_every_line_within_limit():
    from vrc.chatbox import fit_lines
    text, cut = fit_lines("A" * 200, "日" * 200, "한" * 200)
    assert cut and len(text) == MAX_CHARS
    lines = text.splitlines()
    assert len(lines) == 3 and all(line.endswith("…") for line in lines)
    assert lines[0].startswith("A") and lines[1].startswith("日") and lines[2].startswith("한")
    text, cut = fit_lines("Hi", "日" * 200, "한" * 200)
    assert text.startswith("Hi\n") and len(text) == MAX_CHARS and cut


def test_multiline_format_omits_empty_and_repeated_text():
    from vrc.chatbox import fit_lines
    assert fit_lines(" Hello\r\nworld ", "Hello world", "") == ("Hello world", False)
    assert fit_lines("", "", "") == ("", False)
