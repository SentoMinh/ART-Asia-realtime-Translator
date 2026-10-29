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
import heapq
import itertools
import logging
import queue
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from ui.backend import AUTO, LANGS, Utterance
from vrc.translate import TranslateError, translate_targets

from . import services
from .stt import CloudHearing, SttError
from .local_inference import LocalHearing
from .translators import ServiceChain
from .vad import Segment, Segmenter

log = logging.getLogger(__name__)

FIRST_ID = 1_000_000      # typed lines count from 1: these never collide with them
# Detector strictness when the window's settings don't say (Settings → Sound has both sliders):
MIC_THRESHOLD = 0.5       # a microphone is clean: the detector's default is right for it
SPEAKER_THRESHOLD = 0.7   # game sound has music: stricter
STALE_S = 10.0            # speech that waited this long is dropped: stay live
AUDIO_BACKLOG_S = 2.0     # skip capture backlog before spending CPU on voice detection
MAX_AUDIO_CHUNKS = 128    # bounded even when capture callbacks arrive faster than expected
MAX_PENDING_SENTENCES = 8
MAX_PENDING_TRANSLATIONS = 4   # per source, including the translation already running
REPEAT_S = 15.0           # the same line again within this time is music fooling the model
REPORT_S = 30             # how often the log says how much sound arrived
ANNOUNCE_S = 20.0         # "【Speaking Spanish】" is shown again only after this long
MIC, SPEAKER = "mic", "speaker"
RELEASE = "__release_local_hearing__"   # queue marker: drop the local hearing weights


class _PendingSpeech:
    """A small priority queue: keep recent speech, reserving control messages and mic priority."""

    def __init__(self, limit=MAX_PENDING_SENTENCES):
        self.limit = limit
        self._items = []
        self._ready = threading.Condition()
        self._closed = False

    def put(self, item):
        """Never wait for recognition. Return the discarded sentence, if any."""
        with self._ready:
            source = item[2]
            if self._closed:
                return item
            if source is None:
                self._closed = True
                self._items.clear()
            elif source == RELEASE and any(old[2] == RELEASE for old in self._items):
                return None
            self._items.append(item)
            speech = [old for old in self._items if old[2] in (MIC, SPEAKER)]
            discarded = None
            if len(speech) > self.limit:
                # Speakers yield to the microphone; within a source, keep the newest sentence.
                discarded = max(speech, key=lambda old: (old[0], -old[1]))
                self._items.remove(discarded)
            heapq.heapify(self._items)
            self._ready.notify()
            return discarded

    def get(self, block=True, timeout=None):
        with self._ready:
            if not self._items and (not block or not self._ready.wait_for(lambda: self._items, timeout)):
                raise queue.Empty
            return heapq.heappop(self._items)

    def get_nowait(self):
        return self.get(block=False)

    def qsize(self):
        with self._ready:
            return len(self._items)


class SpeechEngine:
    def __init__(self, backend, engines: dict | None = None, translator=None,
                 clock=time.monotonic, vads: dict | None = None):
        self.backend = backend
        self._engines = engines or {"local": LocalHearing()}   # online ones are added when picked
        self._translator = translator or ServiceChain(
            lambda: getattr(backend.settings, "translating", ""))
        if hasattr(self._translator, "on_switch") and getattr(self._translator, "on_switch") is None:
            self._translator.on_switch = self._on_translator_switch
        self._clock = clock
        self._ids = itertools.count(FIRST_ID)
        self._order = itertools.count()
        self._chunks: queue.Queue = queue.Queue(maxsize=MAX_AUDIO_CHUNKS)
        self._audio_lock = threading.Lock()
        self._stopped = threading.Event()
        self._capture_order = {source: itertools.count() for source in (MIC, SPEAKER)}
        self._cut_order = {source: -1 for source in (MIC, SPEAKER)}
        self._sentences = _PendingSpeech()
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
        self._finish_slots = {source: threading.BoundedSemaphore(MAX_PENDING_TRANSLATIONS)
                              for source in (MIC, SPEAKER)}
        self._threads: list[threading.Thread] = []
        backend.on_game_audio = lambda mono, rate: self._capture(SPEAKER, mono, rate)
        backend.on_mic_audio = lambda mono, rate: self._capture(MIC, mono, rate)

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
        with self._audio_lock:
            self._stopped.set()
            while True:
                try:
                    self._chunks.get_nowait()
                except queue.Empty:
                    break
            self._chunks.put_nowait(None)
        self._sentences.put((-1, next(self._order), None, None))
        for pool in (self._pool, self._mic_pool):
            if pool is not None:
                pool.shutdown(wait=False, cancel_futures=True)

    def release_local_hearing(self) -> None:
        """Drop the local hearing model after switching to an online engine. The marker runs on
        the hearing thread, so it never closes a recognizer that is still decoding a sentence."""
        if not self._stopped.is_set():
            self._sentences.put((-2, next(self._order), RELEASE, None))

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

    def _switch_hearing(self, fallback: str = "local") -> None:
        current = getattr(self.backend.settings, "hearing", "")
        if current != fallback:
            log.info("auto-switching hearing from %s to %s", current, fallback)
            if hasattr(self.backend, "settings"):
                self.backend.settings.hearing = fallback
            tell = getattr(self.backend, "setting_switched", None)
            if tell is not None and hasattr(tell, "emit"):
                tell.emit("hearing", fallback)

    def _request_switch(self, category: str, failed_service: str, reason: str = "") -> None:
        tell = getattr(self.backend, "switch_prompt_requested", None)
        if tell is not None and hasattr(tell, "emit"):
            tell.emit(category, failed_service, reason)
        else:
            self._switch_hearing("local")

    def _on_translator_switch(self, name: str) -> None:
        tell = getattr(self.backend, "setting_switched", None)
        if ":" in name:
            svc, model = name.split(":", 1)
            if hasattr(self.backend, "current_translating_service"):
                self.backend.current_translating_service = svc
            if getattr(self.backend, "current_translating_model", "") != model:
                self.backend.current_translating_model = model
                if tell is not None and hasattr(tell, "emit"):
                    tell.emit("translating_model", model)
            if hasattr(self.backend, "settings") and getattr(self.backend.settings, "translating", "") != svc:
                if tell is not None and hasattr(tell, "emit"):
                    tell.emit("translating", svc)
                else:
                    self.backend.settings.translating = svc
        else:
            if getattr(self.backend, "current_translating_model", "") != name:
                self.backend.current_translating_model = name
                if tell is not None and hasattr(tell, "emit"):
                    tell.emit("translating_model", name)

    # ---- cut: sound -> sentences ---------------------------------------------------------

    def _capture(self, source, mono, rate):
        with self._audio_lock:
            if self._stopped.is_set():
                return
            item = (source, mono, rate, next(self._capture_order[source]), self._clock())
            try:
                self._chunks.put_nowait(item)
            except queue.Full:
                try:
                    self._chunks.get_nowait()
                except queue.Empty:
                    pass  # The cutter freed a slot between the two calls.
                self._chunks.put_nowait(item)

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
                source, mono, rate, order, captured_at = item
                if self._clock() - captured_at > AUDIO_BACKLOG_S:
                    continue
                seen = self._seen[source]
                seen["seconds"] += len(mono) / rate
                seen["peak"] = max(seen["peak"], float(abs(mono).max()) if len(mono) else 0.0)
                try:
                    if order != self._cut_order[source] + 1:
                        self._segmenters[source].reset()
                    self._cut_order[source] = order
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
        if self._stopped.is_set():
            return
        self._seen[source]["sentences"] += 1
        self._sentences.put((0 if source == MIC else 1, next(self._order), source, segment))

    # ---- hear: sentence -> text ----------------------------------------------------------

    def _engine(self):
        name = getattr(self.backend.settings, "hearing", "") or services.default_service()
        if name not in self._engines and (name in services.SERVICES or services.is_custom(name)):
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
        settings = self.backend.settings
        if settings.mic_on or settings.subtitles_on:
            try:
                self._status("Loading the speech model…")
                self._engine().load()
                self._status("Listening")
            except SttError as error:
                self._status(self._problem(error))
        while True:
            _, _, source, segment = self._sentences.get()
            if source is None:
                for engine in self._engines.values():
                    if hasattr(engine, "close"):
                        engine.close()
                return
            if source == RELEASE:
                local = self._engines.get("local")
                if (self.backend.settings.hearing != "local" and local is not None
                        and hasattr(local, "close") and local.close()):
                    log.info("released local hearing weights")
                continue
            try:
                self.hear(source, segment)
            except Exception as error:
                log.exception("hearing a %s sentence failed", source)
                self._status(f"the speech engine failed: {error}")

    def hear(self, source: str, segment: Segment) -> None:
        settings = self.backend.settings
        waited = self._clock() - segment.speech_end
        if waited > STALE_S:
            log.info("dropped a sentence that waited %.1f s", waited)
            if source == MIC:
                self._typing("typing_cancelled")
            return
        languages = settings.spoken_languages(source == MIC)
        lang = languages[0] if len(languages) == 1 and languages[0] != AUTO else None
        prefer = tuple(code for code in languages if code != AUTO)
        if not prefer:
            prefer = tuple(dict.fromkeys(code for code in
                           (self.backend.last_heard, *settings.spoken_languages(True)) if code))
        engine = self._engine()
        recognition_started = self._clock()
        fallback_used = False
        try:
            heard = engine.transcribe(segment.samples, lang, prefer=prefer)
        except SttError as error:
            if engine is not self._engines.get("local") and "local" in self._engines:
                local_eng = self._engines["local"]
                if getattr(local_eng, "available", lambda: True)():
                    log.warning("hearing failed on cloud, falling back to local: %s", error)
                    try:
                        heard = local_eng.transcribe(segment.samples, lang, prefer=prefer)
                        fallback_used = True
                        self._request_switch("hearing", getattr(settings, "hearing", ""), str(error))
                    except SttError as local_error:
                        self._status(self._problem(local_error))
                        if source == MIC:
                            self._typing("typing_cancelled")
                        return
                else:
                    self._status(self._problem(error))
                    if source == MIC:
                        self._typing("typing_cancelled")
                    return
            else:
                self._status(self._problem(error))
                if source == MIC:
                    self._typing("typing_cancelled")
                return
        if engine is self._engines.get("local") and getattr(settings, "hearing", "") != "local":
            self._request_switch("hearing", getattr(settings, "hearing", ""), self._missing)
        if (not fallback_used and engine is not self._engines.get("local")
                and self.backend.settings.hearing != "local"):
            # The online engine works again: do not keep the fallback model resident.
            local = self._engines.get("local")
            if local is not None and hasattr(local, "close") and local.close():
                log.info("released local hearing weights")
        log.info("hearing source=%s wait_ms=%d recognition_ms=%d", source, waited * 1000,
                 (self._clock() - recognition_started) * 1000)
        self._status("Listening")
        text = heard.text.strip()
        log.info("%s (%.1f s of sound, %s): %s", source, len(segment.samples) / 16000,
                 heard.lang, text or "(nothing)")
        if not text or not re.search(r"\w", text):
            if source == MIC:
                self._typing("typing_cancelled")
            return
        if len(languages) > 1 and heard.lang not in languages:
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
            target = settings.panel_languages()[0]
        else:
            target = self.backend.speech_target_lang()
        line = Utterance(id=next(self._ids), source=source, original=text,
                         src_lang=heard.lang, dst_lang=target,
                         panel_targets=tuple(settings.panel_languages()),
                         chatbox_targets=tuple(settings.chatbox_languages(self.backend.last_heard))
                         if source == MIC else ())
        if self._stopped.is_set():
            return
        pool = self._mic_pool if source == MIC else self._pool
        if pool is not None:
            slot = self._finish_slots[source]
            if not slot.acquire(blocking=False):
                self._skip_translation(line, segment, "Translation skipped to keep up with live speech")
                return
            try:
                self.backend.utterance.emit(line)          # shown at once, as "translating…"
                future = pool.submit(self._finish_safely, line, segment)
            except Exception:
                slot.release()
                raise
            def completed(done):
                slot.release()
                if done.cancelled():
                    self._skip_translation(line, segment, "Translation cancelled")
            future.add_done_callback(completed)
        else:
            self.backend.utterance.emit(line)
            self.finish(line, segment)

    def _announce(self, lang: str, segment: Segment) -> None:
        """Someone speaks a language the program does not translate (the hearing engine was
        at least 80% sure): the window only says so, e.g. "【Speaking Spanish】". Said once per
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

    def _skip_translation(self, line: Utterance, segment: Segment, note: str) -> None:
        if line.source == MIC:
            self._typing("typing_cancelled")
        self.backend.utterance.emit(dataclasses.replace(
            line, final=True, note=note, latency_ms=int((self._clock() - segment.speech_end) * 1000)))

    def _finish_safely(self, line: Utterance, segment: Segment) -> None:
        try:
            if self._stopped.is_set():
                self._skip_translation(line, segment, "Translation cancelled")
                return
            if self._clock() - segment.speech_end > STALE_S:
                self._skip_translation(line, segment, "Translation skipped after waiting too long")
                return
            self.finish(line, segment)
        except Exception:
            log.exception("finishing a line failed")
            self._skip_translation(line, segment, "Translation failed")

    def finish(self, line: Utterance, segment: Segment) -> None:
        if self._stopped.is_set():
            self._skip_translation(line, segment, "Translation cancelled")
            return
        started = self._clock()
        line = dataclasses.replace(line, final=True)    # a copy: the window holds the first one
        def show_progress(translations):
            ready = tuple((code, translations[code]) for code in line.panel_targets if translations.get(code))
            if ready and not self._stopped.is_set():
                self.backend.utterance.emit(dataclasses.replace(
                    line, final=False, panel_translations=ready,
                    latency_ms=int((self._clock() - segment.speech_end) * 1000)))

        translations, errors = translate_targets(
            self._translator, line.original, (*line.panel_targets, line.dst_lang, *line.chatbox_targets),
            line.src_lang if line.src_lang in LANGS else "", heard=True, on_result=show_progress)
        if self._stopped.is_set():
            self._skip_translation(line, segment, "Translation cancelled")
            return
        line.translation = translations.get(line.dst_lang, "")
        if line.dst_lang == line.src_lang and line.translation == line.original:
            line.translation = ""
        line.panel_translations = tuple((code, translations.get(code, "")) for code in line.panel_targets)
        line.chatbox_translations = tuple((code, translations.get(code, "")) for code in line.chatbox_targets)
        for code, error in errors.items():
            label = "not translated" if code == line.dst_lang else f"not translated ({code})"
            line.note = ", ".join(filter(None, [line.note, f"{label}: {error}"]))
            if isinstance(error, TranslateError):
                tell = getattr(self.backend, "switch_prompt_requested", None)
                if tell is not None and hasattr(tell, "emit"):
                    tell.emit("translating", getattr(self.backend.settings, "translating", ""), str(error))
        if not line.translation:
            line.dst_lang = line.src_lang
        line.latency_ms = int((self._clock() - segment.speech_end) * 1000)
        log.info("translation line=%d targets=%d duration_ms=%d", line.id, len(translations),
                 (self._clock() - started) * 1000)
        log.info("%s line %d done in %d ms: %s %s", line.source, line.id, line.latency_ms,
                 line.translation or "(no translation)", line.note)
        send = line.source == MIC or (line.source == SPEAKER and self.backend.settings.chatbox_speaker)
        if send and hasattr(self.backend, "send_to_chatbox"):
            self.backend.send_to_chatbox(line)           # it shows the line again, with "sent"
        else:
            self.backend.utterance.emit(line)
