"""Example lines and moving level bars, so the window can be tried before the engine exists."""
from __future__ import annotations

import random

from PySide6.QtCore import QTimer

from .backend import AUTO, Backend, Status, Utterance
from .config import Settings

# (who, language spoken, the same line in every language); who 0 = you
SCRIPT = [
    (1, "zh", {"zh": "你好!你是从哪里来的?", "en": "Hi! Where are you from?",
               "vi": "Xin chào! Bạn đến từ đâu vậy?"}),
    (0, "", {"zh": "我来自越南,很高兴认识你。", "en": "I'm from Vietnam, nice to meet you.",
             "vi": "Mình đến từ Việt Nam, rất vui được gặp bạn."}),
    (2, "en", {"zh": "这个世界太漂亮了,你以前来过吗?",
               "en": "This world looks amazing, have you been here before?",
               "vi": "Thế giới này đẹp quá, bạn từng đến đây chưa?"}),
    (1, "zh", {"zh": "我第一次来,我们一起去看看吧。",
               "en": "It's my first time here, let's look around together.",
               "vi": "Mình mới đến lần đầu, cùng đi xem thử nhé."}),
    (0, "", {"zh": "好,走吧!", "en": "Okay, let's go!", "vi": "Được, đi thôi!"}),
]
STEP_MS = 60      # one tick of the level bars
PAUSE_TICKS = 25  # silence between lines


class DemoBackend(Backend):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = Settings()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._next_id = 1
        self._line = 0
        self._pos = 0          # characters "heard" so far in the current line
        self._pause = PAUSE_TICKS
        self._current: Utterance | None = None
        self._last_heard = "en"

    def start(self) -> None:
        self.status_changed.emit(Status(
            "warn", "Demo", "The translator engine is not connected yet. These lines are examples."))
        self._timer.start(STEP_MS)

    def stop(self) -> None:
        self._timer.stop()

    def apply_settings(self, settings) -> None:
        self.settings = settings

    def send_text(self, text: str) -> None:
        self.utterance.emit(Utterance(
            id=self._take_id(), source="typed", original=text, src_lang=self.settings.spoken_languages(True)[0],
            panel_targets=tuple(self.settings.panel_languages()),
            dst_lang=self.target_lang(), final=True, sent=False,
            note="demo: no engine yet, nothing was translated or sent"))

    def _take_id(self) -> int:
        self._next_id += 1
        return self._next_id - 1

    def target_lang(self) -> str:
        return self.target_langs()[0]

    def target_langs(self) -> list[str]:
        return self.settings.chatbox_languages(self._last_heard, typed=True)

    def speech_target_lang(self) -> str:
        return self.settings.chatbox_languages(self._last_heard)[0]

    def _tick(self) -> None:
        who, lang, texts = SCRIPT[self._line % len(SCRIPT)]
        mine = who == 0
        enabled = self.settings.mic_on if mine else self.settings.subtitles_on
        talking = self._pause == 0 and enabled
        loud = random.uniform(0.35, 0.9) if talking else 0.0
        self.mic_level.emit(loud if mine else 0.0)
        self.speaker_level.emit(0.0 if mine else loud)
        if self._pause:
            self._pause -= 1
            return
        if not enabled:
            self._advance()
            return
        src = self.settings.spoken_languages(True)[0] if mine else lang
        dst = self.speech_target_lang() if mine else self.settings.panel_languages()[0]
        heard = texts.get(src, texts["en"])
        if self._current is None:
            self._current = Utterance(id=self._take_id(), source="mic" if mine else "speaker",
                                      speaker=who, src_lang=src, dst_lang=dst,
                                      panel_targets=tuple(self.settings.panel_languages()))
        self._pos += 1 if src == "zh" else 3
        u = self._current
        u.original = heard[:self._pos]
        if self._pos >= len(heard):
            u.final = True
            u.translation = "" if src == dst else texts.get(dst, "")
            u.panel_translations = tuple((code, texts.get(code, "")) for code in u.panel_targets)
            u.latency_ms = random.randint(600, 1400)
            if mine:
                u.sent = False
                u.note = "demo: nothing was sent"
            else:
                self._last_heard = src
            self._advance()
        self.utterance.emit(u)

    def _advance(self) -> None:
        self._line += 1
        self._pos = 0
        self._pause = PAUSE_TICKS
        self._current = None
