"""The real VRChat connection: shows whether VRChat is found, captures VRChat's sound and the
microphone (level bars), translates typed text and sends it to the chatbox.

Turning the captured sound into text is not connected yet: that engine is still being
benchmarked. It plugs into on_game_audio / on_mic_audio.
"""
from __future__ import annotations

import queue
import threading
import time
from collections import deque

from PySide6.QtCore import QTimer, Signal

from vrc.chatbox import MIN_GAP_S, Chatbox, TypingDots, VRChatState, find_vrchat, fit, fit_bilingual
from vrc.translate import NoTranslator, TranslateError

from .backend import AUTO, Backend, Status, Utterance
from .config import Settings

try:
    from vrc import audio
except ImportError:      # numpy missing: the window still works, without sound
    audio = None

POLL_MS = 2000
LEVEL_MS = 50           # how often the level bars move
DEFAULT_TARGET = "en"   # everything on Auto and nobody was heard yet


class LiveBackend(Backend):
    _translated = Signal(object, str, str, int)   # utterance, translation, error, ms (from the worker)
    _chatbox_request = Signal(object)             # utterance (from the speech engine's thread)

    def __init__(self, chatbox=None, find=find_vrchat, clock=time.monotonic, translator=None,
                 threaded: bool = True, game_audio=None, mic_audio=None, parent=None, output_audio=None):
        super().__init__(parent)
        self.settings = Settings()
        self.state = VRChatState()
        self.last_heard = ""          # language of the last other player heard (speech engine, later)
        # sound: VRChat's own output and the microphone (factories, so tests can pass fakes)
        self._game_factory = game_audio or (audio.GameAudio if audio else None)
        self._output_factory = output_audio or (audio.OutputAudio if audio else None)
        self._speaker_device = ""
        self._mic_factory = mic_audio or (audio.MicAudio if audio else None)
        self._game = None
        self._game_pid = 0
        self._mic = None
        self._mic_device = ""
        self.game_problem = ""        # why VRChat's sound is not captured; "" when it is
        self.mic_problem = ""
        # the speech engine plugs in here: called with (mono float32 array, sample rate) on an
        # audio thread, so it must only queue the chunk and return
        self.on_game_audio = None
        self.on_mic_audio = None
        self.speech_ready = False     # set once the speech engine is attached (ui.main.attach_speech)
        self.speech_problem = ""      # why it is not, shown in the status tooltip
        self.speech_status = ""       # set by the engine from its threads: "Loading…", "Listening"
        self.update_note = ""         # set by ui/updater.py when a new version waits for the next start
        self._level_timer = QTimer(self)
        self._level_timer.timeout.connect(self._emit_levels)
        self._chatbox = chatbox or Chatbox()
        self._find = find
        self._clock = clock
        self._dots = TypingDots(self._chatbox, clock=clock)   # "typing…" before a first message
        self._translator = translator or NoTranslator()
        self._threaded = threaded
        self._jobs: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self._outbox: deque[tuple[Utterance, str]] = deque()   # (line, text for the chatbox)
        self._last_sent = -MIN_GAP_S
        self._next_id = 1
        self._translated.connect(self._on_translated)
        self._chatbox_request.connect(self._queue_for_chatbox)
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self.poll)
        self._send_timer = QTimer(self)
        self._send_timer.setSingleShot(True)
        self._send_timer.timeout.connect(self.pump)

    def start(self) -> None:
        self.poll()
        self._poll_timer.start(POLL_MS)
        self._level_timer.start(LEVEL_MS)
        if self._threaded:
            self._worker = threading.Thread(target=self._work, name="translate", daemon=True)
            self._worker.start()
            self._jobs.put(("prepare",))

    def stop(self) -> None:
        self._poll_timer.stop()
        self._send_timer.stop()
        self._level_timer.stop()
        self._jobs.put(None)
        self._dots.cancelled()
        self._stop_source("_game")
        self._stop_source("_mic")

    def apply_settings(self, settings) -> None:
        self.settings = settings
        if not settings.chatbox_speaker:
            self._outbox = deque((line, text) for line, text in self._outbox if line.source != "speaker")
        if not settings.chatbox_typing or not settings.mic_on:
            self._dots.cancelled()
        if self._poll_timer.isActive():   # running: switches and the microphone choice act at once
            self._sync_audio()
            self._emit_status()

    def poll(self) -> None:
        self.state = self._find()
        self._sync_audio()
        self._emit_status()

    def _emit_status(self) -> None:
        if not self.state.running:
            status = Status("error", "VRChat not found", "Start VRChat. The window finds it by itself.")
        elif not self.state.listening:
            status = Status("warn", "OSC is off", "VRChat is running but does not listen for chatbox "
                            "messages. In VRChat: Action Menu → Options → OSC → Enabled.")
        else:
            status = Status("ok", "Connected", "VRChat is running and takes chatbox messages. Typed "
                            "text is translated and sent.")
        lines = [status.detail]
        if (self.state.running or self.settings.speaker_device) and self.settings.subtitles_on:
            captured = self.settings.speaker_device or "VRChat's sound"
            if self._game and self.speech_ready:
                lines.append(f"{captured} is being captured and turned into text.")
                if self.speech_status:
                    lines.append(f"Speech engine: {self.speech_status}")
            elif self._game:
                lines.append(f"{captured} is being captured. Turning speech into text is not connected yet.")
                if self.speech_problem:
                    lines.append(f"Speech engine: {self.speech_problem}")
            else:
                lines.append(f"{captured} is not captured: {self.game_problem}")
                if status.level == "ok":
                    status.level, status.text = "warn", "No game sound"
        if self.settings.mic_on and not self._mic:
            lines.append(f"Your microphone is not captured: {self.mic_problem}")
        if self.update_note:
            lines.append(self.update_note)
        status.detail = "\n".join(lines)
        self.status_changed.emit(status)

    # ---- sound ----------------------------------------------------------------------

    def _stop_source(self, name: str) -> None:
        source = getattr(self, name)
        setattr(self, name, None)
        if source is not None:
            try:
                source.stop()
            except Exception:
                pass   # it is being thrown away anyway

    def _sync_audio(self) -> None:
        """Start or stop the two captures so they match VRChat's state and the switches."""
        device = self.settings.speaker_device
        want_game = self.settings.subtitles_on and (bool(device) or self.state.running)
        if self._game and (not want_game or self._speaker_device != device
                           or (not device and self._game_pid != self.state.pid)):
            self._stop_source("_game")
        if want_game and not self._game:
            self._game, self.game_problem = self._open(
                self._output_factory if device else self._game_factory,
                device if device else self.state.pid, lambda mono, rate: self._forward("game", mono, rate))
            self._speaker_device = device
            self._game_pid = self.state.pid
        want_mic = self.settings.mic_on
        if self._mic and (not want_mic or self._mic_device != self.settings.mic_device):
            self._stop_source("_mic")
        if want_mic and not self._mic:
            self._mic, self.mic_problem = self._open(
                self._mic_factory, self.settings.mic_device,
                lambda mono, rate: self._forward("mic", mono, rate))
            self._mic_device = self.settings.mic_device

    @staticmethod
    def _open(factory, target, on_audio):
        """(running source, "") or (None, why it failed)."""
        if factory is None:
            return None, "the audio packages are not installed"
        try:
            source = factory(target, on_audio)
            source.start()
            return source, ""
        except Exception as error:
            return None, str(error) or type(error).__name__

    def _forward(self, which: str, mono, rate: int) -> None:
        listener = self.on_game_audio if which == "game" else self.on_mic_audio
        if listener is not None:
            listener(mono, rate)

    def _emit_levels(self) -> None:
        self.speaker_level.emit(self._game.level() if self._game else 0.0)
        self.mic_level.emit(self._mic.level() if self._mic else 0.0)

    def target_lang(self) -> str:
        """The language typed text is translated into: the one picked next to Send, else the
        language heard last from audio, else "They speak", else English."""
        if self.settings.send_lang != AUTO:
            return self.settings.send_lang
        if self.last_heard:
            return self.last_heard
        their = self.settings.their_lang
        return their if their != AUTO else DEFAULT_TARGET

    def speech_target_lang(self) -> str:
        """Voice replies follow 'They speak'; only Auto follows the last player heard."""
        their = self.settings.their_lang
        return their if their != AUTO else self.last_heard or DEFAULT_TARGET

    # ---- "typing…" in VRChat: only before the first message after a quiet time ----------

    def typing_started(self) -> None:
        """The speech engine heard me start talking. Safe from any thread."""
        if self.settings.chatbox_typing and self.settings.mic_on:
            self._dots.starting()

    def typing_cancelled(self) -> None:
        """What I started saying won't be sent (a cough, nothing heard). Safe from any thread."""
        self._dots.cancelled()

    # ---- typed text: translate, then send -------------------------------------------

    def send_text(self, text: str) -> None:
        text = " ".join(text.split())
        if not text:
            return
        utterance = Utterance(id=self._next_id, source="typed", original=text,
                              src_lang=self.settings.my_lang, dst_lang=self.target_lang())
        self._next_id += 1
        self.utterance.emit(utterance)   # shown at once as "translating…"
        if self.settings.chatbox_typing:
            self._dots.starting()
        job = ("translate", utterance, utterance.dst_lang, utterance.src_lang)
        if self._threaded:
            self._jobs.put(job)
        else:
            self._run(job)

    def _work(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            self._run(job)

    def _run(self, job: tuple) -> None:
        if job[0] == "prepare":
            self._translator.prepare()
            return
        _, utterance, target, source = job
        started = time.perf_counter()
        translation, error = "", ""
        try:
            translation = self._translator.translate(utterance.original, target, source)
        except TranslateError as problem:
            error = str(problem)
        except Exception as problem:   # the worker must survive anything, or typing goes silent
            error = f"translation failed: {problem}"
        self._translated.emit(utterance, translation, error, int((time.perf_counter() - started) * 1000))

    def _on_translated(self, utterance: Utterance, translation: str, error: str, ms: int) -> None:
        utterance.final = True
        utterance.translation = translation
        notes = []
        if error:
            notes.append(f"not translated: {error}")
            utterance.dst_lang = utterance.src_lang     # the row shows only the typed text
        else:
            utterance.latency_ms = ms
        utterance.note = ", ".join(notes)
        self._queue_for_chatbox(utterance)

    def send_to_chatbox(self, utterance: Utterance, text: str | None = None) -> None:
        """Send a finished line to VRChat. Other players need Add Speaker words enabled;
        their translation includes the original. `text`, if given, is used as the translation.
        Safe to call from any thread; the line is emitted again through `utterance` with
        `sent` filled in."""
        if text is not None and text != utterance.original:
            utterance.translation = text
        self._chatbox_request.emit(utterance)

    def _queue_for_chatbox(self, utterance: Utterance) -> None:
        speaker = utterance.source == "speaker"
        if speaker and not self.settings.chatbox_speaker:
            self.utterance.emit(utterance)   # switched off while a worker's result was on its way
            return
        notes = [utterance.note] if utterance.note else []
        translation = utterance.translation
        if speaker:
            outgoing, cut = fit_bilingual(translation, utterance.original)
        else:
            outgoing = translation or utterance.original
            if translation and self.settings.chatbox_original and translation != utterance.original:
                outgoing = f"{translation} ({utterance.original})"
            outgoing, cut = fit(outgoing)
        if cut:
            notes.append("cut to 144 characters")
        self.poll()
        if not self.state.ready:
            utterance.sent = False
            self._dots.cancelled()
            notes.append("VRChat is not running" if not self.state.running else "OSC is off in VRChat")
        else:
            self._outbox.append((utterance, outgoing))
        utterance.note = ", ".join(notes)
        self.utterance.emit(utterance)
        self.pump()

    def _wait_s(self) -> float:
        return max(self._last_sent + MIN_GAP_S - self._clock(), 0.0)

    def pump(self) -> None:
        """Send the next waiting message, keeping VRChat's gap between messages."""
        if not self._outbox:
            return
        wait = self._wait_s()
        if wait > 0:
            self._send_timer.start(int(wait * 1000) + 10)
            return
        utterance, outgoing = self._outbox.popleft()
        try:
            self._chatbox.send(outgoing)
            utterance.sent = True
            self._dots.sent()
        except OSError as error:
            utterance.sent = False
            self._dots.cancelled()
            utterance.note = ", ".join(filter(None, [utterance.note, f"could not send: {error}"]))
        self._last_sent = self._clock()
        self.utterance.emit(utterance)
        if self._outbox:
            self._send_timer.start(int(MIN_GAP_S * 1000) + 10)
