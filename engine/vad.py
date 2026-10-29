"""Cuts live sound into sentences.

A voice detector (Silero VAD v6, MIT licence; the model file is engine/assets/silero_vad_v6.onnx,
1.2 MB, run on the CPU by onnxruntime) gives every 32 ms of sound a "someone is speaking"
probability. A sentence starts when that passes the threshold
and ends after a short silence. Higher thresholds reject more noise but can miss quiet words.
The threshold is held for each sentence, so moving the slider cannot cut it off midway.

With the detector off, the sound is cut by the clock instead (worse: it cuts inside words and
lets music through, so the speech model makes up more text).
"""
from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

MODEL_FILE = Path(__file__).resolve().parent / "assets" / "silero_vad_v6.onnx"
RATE = 16000              # what the detector and the speech models take
FRAME = 512               # 32 ms: the piece size Silero VAD works on
CONTEXT = 64              # samples of the previous piece it wants in front of each one
FRAME_S = FRAME / RATE

PRE_ROLL_S = 0.3          # kept from before the voice started, so first sounds aren't lost
SILENCE_S = 0.8           # this much quiet ends a sentence (0.55 cut people off at every breath)
KEEP_SILENCE_S = 0.2      # of which this much stays at the end of the sentence
MIN_SPEECH_S = 0.25       # shorter than this is a click or a cough, not a sentence
MAX_S = 12.0              # a longer sentence is cut here, to keep the delay bounded
OFF_BELOW = 0.15          # a sentence continues until the probability is this far under the threshold
CLOCK_S = 4.0             # detector off: one piece every this many seconds
QUIET_RMS = 0.003         # detector off: pieces quieter than this (about -50 dB) are skipped


class SileroVad:
    """Speech probability per 32 ms piece, remembering what came before between calls."""

    def __init__(self):
        import onnxruntime
        options = onnxruntime.SessionOptions()
        options.inter_op_num_threads = 1      # it is tiny: more threads only fight the game
        options.intra_op_num_threads = 1
        options.log_severity_level = 4
        self._session = onnxruntime.InferenceSession(
            str(MODEL_FILE), providers=["CPUExecutionProvider"], sess_options=options)
        self.reset()

    def reset(self) -> None:
        self._h = np.zeros((1, 1, 128), dtype="float32")
        self._c = np.zeros((1, 1, 128), dtype="float32")
        self._tail = np.zeros(CONTEXT, dtype="float32")

    def probabilities(self, samples: np.ndarray) -> np.ndarray:
        """`samples`: a whole number of pieces of FRAME samples. Returns one value per piece."""
        pieces = samples.reshape(-1, FRAME)
        context = np.vstack([self._tail, pieces[:-1, -CONTEXT:]])
        output, self._h, self._c = self._session.run(
            None, {"input": np.concatenate([context, pieces], axis=1), "h": self._h, "c": self._c})
        self._tail = pieces[-1, -CONTEXT:].copy()
        return output.reshape(-1)


@dataclass
class Segment:
    samples: np.ndarray       # 16 kHz mono float32: one sentence
    speech_end: float         # on the clock, when the person stopped talking
    forced: bool = False      # cut because it got too long, or by the clock


class Segmenter:
    """feed() it sound as it arrives (any sample rate); on_segment(Segment) is called for
    every sentence. Use one per sound source, from one thread.

    on_start() is called when someone starts talking, on_drop() when that talking ended
    without a sentence (too short: a cough, a click). Both only with the detector on."""

    def __init__(self, on_segment: Callable[[Segment], None], vad=None, threshold: float = 0.7,
                 vad_on: bool = True, clock: Callable[[], float] = time.monotonic,
                 on_start: Callable[[], None] | None = None,
                 on_drop: Callable[[], None] | None = None):
        self._on_segment = on_segment
        self._on_start = on_start
        self._on_drop = on_drop
        self._vad = vad
        self._clock = clock
        self.threshold = threshold
        self._sentence_threshold = threshold
        self.vad_on = vad_on
        self._resampler = None
        self._resampler_rate = 0
        self._left = np.zeros(0, dtype="float32")      # samples that don't fill a piece yet
        self._pre: deque[np.ndarray] = deque(maxlen=round(PRE_ROLL_S / FRAME_S))
        self._pieces: list[np.ndarray] = []
        self._talking = False
        self._silent = 0          # pieces of quiet in a row, while talking
        self._spoken = 0          # pieces with speech in this sentence

    def configure(self, vad_on: bool, threshold: float) -> None:
        if vad_on != self.vad_on:
            self._drop()
        self.vad_on, self.threshold = vad_on, threshold

    def feed(self, mono: np.ndarray, rate: int) -> None:
        samples = self._to_16k(mono, rate)
        if self._left.size:
            samples = np.concatenate([self._left, samples])
        whole = samples.size - samples.size % FRAME
        self._left = samples[whole:]
        if not whole:
            return
        samples = samples[:whole]
        if not self.vad_on:
            self._by_clock(samples)
            return
        if self._vad is None:
            self._vad = SileroVad()
        for piece, probability in zip(samples.reshape(-1, FRAME), self._vad.probabilities(samples)):
            self._step(piece, float(probability))

    def flush(self) -> None:
        """The source stopped: hand out what was being said."""
        if self._talking or (not self.vad_on and self._pieces):
            self._emit(forced=True)
        self._drop()

    def reset(self) -> None:
        """Discard interrupted capture, including resampler history, without emitting speech."""
        self._drop()
        self._resampler = None
        self._resampler_rate = 0

    # ---- inside ---------------------------------------------------------------------------

    def _to_16k(self, mono: np.ndarray, rate: int) -> np.ndarray:
        mono = np.asarray(mono, dtype="float32")
        if rate == RATE:
            return mono
        if self._resampler is None or self._resampler_rate != rate:
            import soxr
            self._resampler = soxr.ResampleStream(rate, RATE, 1, dtype="float32")
            self._resampler_rate = rate
        return self._resampler.resample_chunk(mono)

    def _step(self, piece: np.ndarray, probability: float) -> None:
        if not self._talking:
            self._pre.append(piece)
            if probability >= self.threshold:
                self._sentence_threshold = self.threshold  # Slider changes apply to the next sentence.
                self._pieces = list(self._pre)
                self._pre.clear()
                self._talking, self._silent, self._spoken = True, 0, 1
                if self._on_start is not None:
                    self._on_start()
            return
        self._pieces.append(piece)
        if probability >= self._sentence_threshold - OFF_BELOW:
            self._silent = 0
            if probability >= self._sentence_threshold:
                self._spoken += 1
        else:
            self._silent += 1
        if self._silent * FRAME_S >= SILENCE_S:
            self._emit(forced=False)
        elif len(self._pieces) * FRAME_S >= MAX_S:
            self._emit(forced=True)

    def _by_clock(self, samples: np.ndarray) -> None:
        self._pieces.extend(samples.reshape(-1, FRAME))
        if len(self._pieces) * FRAME_S >= CLOCK_S:
            sound = np.concatenate(self._pieces)
            self._pieces = []
            if float(np.sqrt(np.mean(np.square(sound)))) >= QUIET_RMS:
                self._on_segment(Segment(sound, self._clock(), forced=True))

    def _emit(self, forced: bool) -> None:
        keep = len(self._pieces) - max(self._silent - round(KEEP_SILENCE_S / FRAME_S), 0)
        enough = self._spoken * FRAME_S >= MIN_SPEECH_S
        pieces, silent = self._pieces[:keep], self._silent
        self._pieces, self._talking, self._silent, self._spoken = [], False, 0, 0
        if enough and pieces:
            self._on_segment(Segment(np.concatenate(pieces), self._clock() - silent * FRAME_S, forced))
        elif self._on_drop is not None:
            self._on_drop()

    def _drop(self) -> None:
        if self._talking and self._on_drop is not None:
            self._on_drop()
        self._pieces, self._talking, self._silent, self._spoken = [], False, 0, 0
        self._pre.clear()
        self._left = np.zeros(0, dtype="float32")
        if self._vad is not None:
            self._vad.reset()
