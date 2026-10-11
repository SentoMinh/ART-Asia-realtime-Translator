"""Connects sound capture, speech-to-text and translation to the window.

    VRChat's sound ─┐                 ┌─ other players: translated into my language, shown
                    ├─ sentences ─ text ─ translation ─┤
    my microphone ──┘                 └─ me: translated into their language, sent to the chatbox

Three kinds of threads, so that no step waits for another:
  cut     turns the incoming sound into sentences (voice detector)
  hear    turns one sentence at a time into text (the GPU or online); my own voice goes first
  finish  translates (network), two at a time
"""
from __future__ import annotations

import dataclasses
import itertools
import logging
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from ui.backend import AUTO, LANGS, Utterance
from vrc.translate import TranslateError

from . import services
from .stt import CloudHearing, LocalWhisper, SttError
from .translators import ServiceChain
from .vad import Segment, Segmenter

log = logging.getLogger(__name__)

FIRST_ID = 1_000_000      # typed lines count from 1: these never collide with them
# Detector strictness when the window's settings don't say (Settings → Sound has both sliders):
MIC_THRESHOLD = 0.5       # a microphone is clean: the detector's default is right for it
SPEAKER_THRESHOLD = 0.7   # game sound has music: stricter
STALE_S = 10.0            # another player's sentence that waited this long is dropped: stay live
REPEAT_S = 15.0           # the same line again within this time is music fooling the model
REPORT_S = 30             # how often the log says how much sound arrived
ANNOUNCE_S = 20.0         # "【Speaking Korean】" is shown again only after this long
MIC, SPEAKER = "mic", "speaker"


class SpeechEngine:
    def __init__(self, backend, engines: dict | None = None, translator=None,
                 clock=time.monotonic, vads: dict | None = None):
        self.backend = backend
        self._engines = engines or {"local": LocalWhisper()}   # online ones are added when picked
        self._translator = translator or ServiceChain(
            lambda: getattr(backend.settings, "translating", ""))
        self._clock = clock
        self._ids = itertools.count(FIRST_ID)
        self._order = itertools.count()
        self._chunks: queue.Queue = queue.Queue()
        self._sentences: queue.PriorityQueue = queue.PriorityQueue()
        vads = vads or {}
        self._segmenters = {
            SPEAKER: Segmenter(lambda s: self._queue(SPEAKER, s), vad=vads.get(SPEAKER),
                               threshold=SPEAKER_THRESHOLD, clock=clock),
            MIC: Segmenter(lambda s: self._queue(MIC, s), vad=vads.get(MIC),
                           threshold=MIC_THRESHOLD, clock=clock,
                           on_start=lambda: self._typing("typing_started"),
                           on_drop=lambda: self._typing("typing_cancelled"))}
        self._last_line = ("", 0.0)
        self._announced = ("", 0.0)   # the other language announced last, and when
        self._missing = ""        # what the chosen hearing engine lacks, when another one stands in
        self._seen = {source: {"seconds": 0.0, "peak": 0.0, "sentences": 0} for source in (SPEAKER, MIC)}
        self._pool: ThreadPoolExecutor | None = None
        self._mic_pool: ThreadPoolExecutor | None = None
        self._threads: list[threading.Thread] = []
        backend.on_game_audio = lambda mono, rate: self._chunks.put((SPEAKER, mono, rate))
        backend.on_mic_audio = lambda mono, rate: self._chunks.put((MIC, mono, rate))

    # ---- life ---------------------------------------------------------------------------

    def start(self) -> None:
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="finish")
        # my own lines one at a time: the chatbox must get them in the order they were said
        self._mic_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="finish-mic")
        for name, loop in (("cut", self._cut_loop), ("hear", self._hear_loop)):
            thread = threading.Thread(target=loop, name=name, daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        self._chunks.put(None)
        self._sentences.put((-1, next(self._order), None, None))
        for pool in (self._pool, self._mic_pool):
            if pool is not None:
                pool.shutdown(wait=False, cancel_futures=True)

    def _typing(self, what: str) -> None:
        """Tell the window that I started talking ("typing_started") or that it came to nothing
        ("typing_cancelled"); it shows VRChat's typing dots before a first message."""
        tell = getattr(self.backend, what, None)
        if tell is not None:
            tell()

    def _status(self, text: str) -> None:
        if getattr(self.backend, "speech_status", None) != text:
            log.info("status: %s", text)
        self.backend.speech_status = text

    # ---- cut: sound -> sentences ---------------------------------------------------------

    def _cut_loop(self) -> None:
        report_at = self._clock() + REPORT_S
        while True:
            try:
                item = self._chunks.get(timeout=REPORT_S)
            except queue.Empty:
                item = ()
            if item is None:
                return
            if item:
                source, mono, rate = item
                seen = self._seen[source]
                seen["seconds"] += len(mono) / rate
                seen["peak"] = max(seen["peak"], float(abs(mono).max()) if len(mono) else 0.0)
                try:
                    self.cut(source, mono, rate)
                except Exception as error:      # the thread must survive, or the app goes deaf
                    log.exception("cutting %s sound failed", source)
                    self._status(f"the voice detector failed: {error}")
            if self._clock() >= report_at:
                report_at = self._clock() + REPORT_S
                self._report()

    def _report(self) -> None:
        """One log line per half minute: did sound arrive, how loud, how many sentences."""
        log.info("last %d s: %s", REPORT_S, "; ".join(
            f"{source} {seen['seconds']:.0f} s of sound, loudest {seen['peak']:.3f}, "
            f"{seen['sentences']} sentences" for source, seen in self._seen.items()))
        for seen in self._seen.values():
            seen.update(seconds=0.0, peak=0.0, sentences=0)

    def cut(self, source: str, mono, rate: int) -> None:
        settings = self.backend.settings
        if source == MIC:
            threshold = getattr(settings, "mic_vad_sensitivity", MIC_THRESHOLD)
        else:
            threshold = getattr(settings, "vad_sensitivity", SPEAKER_THRESHOLD)
        segmenter = self._segmenters[source]
        segmenter.configure(settings.vad_on, threshold)
        segmenter.feed(mono, rate)

    def _queue(self, source: str, segment: Segment) -> None:
        self._seen[source]["sentences"] += 1
        self._sentences.put((0 if source == MIC else 1, next(self._order), source, segment))

    # ---- hear: sentence -> text ----------------------------------------------------------

    def _engine(self):
        name = getattr(self.backend.settings, "hearing", "") or services.default_service()
        if name not in self._engines and name in services.SERVICES:
            self._engines[name] = CloudHearing(name)
        engine = self._engines.get(name) or self._engines["local"]
        self._missing = ""
        if not getattr(engine, "available", lambda: True)():
            # hear on this PC instead, and say what the chosen service lacks
            self._missing = getattr(engine, "missing", lambda: "the hearing service is not set up")()
            engine = self._engines["local"]
        return engine

    def _problem(self, error: Exception) -> str:
        """Why nothing is heard. If the online service was skipped for its missing key, say
        that too: on a PC without the local model it is the thing to fix."""
        return f"{self._missing}, and {error}" if self._missing else str(error)

    def _hear_loop(self) -> None:
        try:
            self._status("Loading the speech model…")
            self._engine().load()
            self._status("Listening")
        except SttError as error:
            self._status(self._problem(error))
        while True:
            _, _, source, segment = self._sentences.get()
            if source is None:
                return
            try:
                self.hear(source, segment)
            except Exception as error:
                log.exception("hearing a %s sentence failed", source)
                self._status(f"the speech engine failed: {error}")

    def hear(self, source: str, segment: Segment) -> None:
        settings = self.backend.settings
        waited = self._clock() - segment.speech_end
        if source == SPEAKER and waited > STALE_S:
            log.info("dropped a sentence that waited %.1f s", waited)
            return
        if source == MIC:
            lang = settings.my_lang
        else:
            lang = None if settings.their_lang == AUTO else settings.their_lang
        prefer = tuple(code for code in (self.backend.last_heard, settings.my_lang) if code)
        try:
            heard = self._engine().transcribe(segment.samples, lang, prefer=prefer)
        except SttError as error:
            self._status(self._problem(error))
            if source == MIC:
                self._typing("typing_cancelled")
            return
        self._status("Listening")
        text = heard.text.strip()
        log.info("%s (%.1f s of sound, %s): %s", source, len(segment.samples) / 16000,
                 heard.lang, text or "(nothing)")
        if not text:
            if source == MIC:
                self._typing("typing_cancelled")
            return
        if source == SPEAKER and heard.lang not in LANGS:
            self._announce(heard.lang, segment)
            return
        if source == SPEAKER:
            if self._is_repeat(text):
                return
            if heard.lang in LANGS:
                self.backend.last_heard = heard.lang
            target = settings.my_lang
        else:
            target = self.backend.speech_target_lang()
        line = Utterance(id=next(self._ids), source=source, original=text,
                         src_lang=heard.lang, dst_lang=target)
        self.backend.utterance.emit(line)          # shown at once, as "translating…"
        pool = self._mic_pool if source == MIC else self._pool
        if pool is not None:
            pool.submit(self._finish_safely, line, segment)
        else:
            self.finish(line, segment)

    def _announce(self, lang: str, segment: Segment) -> None:
        """Someone speaks a language the program does not translate (the hearing engine was
        at least 80% sure): the window only says so, e.g. "【Speaking Korean】". Said once per
        while, not for every sentence, and "the language heard last" stays as it was."""
        last, when = self._announced
        if lang == last and self._clock() - when < ANNOUNCE_S:
            return
        self._announced = (lang, self._clock())
        self.backend.utterance.emit(Utterance(
            id=next(self._ids), source=SPEAKER, src_lang=lang, final=True,
            latency_ms=int((self._clock() - segment.speech_end) * 1000)))

    def _is_repeat(self, text: str) -> bool:
        key = "".join(ch for ch in text.lower() if ch.isalnum())
        last, when = self._last_line
        self._last_line = (key, self._clock())
        return key == last and self._clock() - when < REPEAT_S

    # ---- finish: text -> translation -> window / chatbox ---------------------------------

    def _finish_safely(self, line: Utterance, segment: Segment) -> None:
        try:
            self.finish(line, segment)
        except Exception:
            log.exception("finishing a line failed")

    def finish(self, line: Utterance, segment: Segment) -> None:
        line = dataclasses.replace(line, final=True)    # a copy: the window holds the first one
        if line.src_lang == line.dst_lang:
            pass                                         # already in the wanted language
        else:
            try:
                line.translation = self._translator.translate(
                    line.original, line.dst_lang, line.src_lang if line.src_lang in LANGS else "",
                    heard=True)
            except TranslateError as error:
                line.note = f"not translated: {error}"
            except Exception as error:
                line.note = f"not translated: {error}"
        if not line.translation:
            line.dst_lang = line.src_lang                # the row then shows only the heard text
        line.latency_ms = int((self._clock() - segment.speech_end) * 1000)
        log.info("%s line %d done in %d ms: %s %s", line.source, line.id, line.latency_ms,
                 line.translation or "(no translation)", line.note)
        send = line.source == MIC or (line.source == SPEAKER and self.backend.settings.chatbox_speaker)
        if send and hasattr(self.backend, "send_to_chatbox"):
            self.backend.send_to_chatbox(line)           # it shows the line again, with "sent"
        else:
            self.backend.utterance.emit(line)
