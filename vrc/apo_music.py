"""Audio sources for an already attached microphone APO.

Run playback functions on a dedicated worker thread. They never open a microphone
or change Windows configuration. ApoPlayer owns the capture-stream lifetime.
"""
from __future__ import annotations

from pathlib import Path
import threading
import time
import wave

import numpy as np
import soxr

from . import audio
from .apo_transport import ApoTransport
from .music import AudioBuffer, RATE, requires_device_routing

FRAMES = 480


def wav_blocks(path: Path):
    """Stream PCM16 mono/stereo WAV as bounded 48 kHz stereo float buffers."""
    with wave.open(str(path), "rb") as source:
        channels, rate = source.getnchannels(), source.getframerate()
        if source.getsampwidth() != 2 or channels not in (1, 2) or not 8000 <= rate <= 192000:
            raise ValueError("Choose a 16-bit PCM WAV file with one or two channels (8–192 kHz).")
        converter = soxr.ResampleStream(rate, RATE, 2, dtype="float32")
        while True:
            raw = source.readframes(max(1, rate // 100))
            samples = np.frombuffer(raw, dtype="<i2").astype(np.float32).reshape(-1, channels) / 32768
            if channels == 1:
                samples = np.repeat(samples, 2, axis=1)
            converted = converter.resample_chunk(samples, last=not raw)
            for offset in range(0, len(converted), FRAMES):
                yield converted[offset:offset + FRAMES]
            if not raw:
                return


class _Pacer:
    def __init__(self, stop):
        self.stop = stop
        self.deadline = time.monotonic()

    def wait(self, frames):
        # Avoid sending a burst of old audio after a stalled worker resumes.
        self.deadline = max(self.deadline + frames / RATE, time.monotonic())
        return self.stop.wait(max(0, self.deadline - time.monotonic()))


def play_file(library: Path, endpoint_token: str, path: Path, stop: threading.Event,
              *, gain=0.5, local_test=False, on_level=None):
    """Play one WAV, closing the sender on completion, cancellation or failure."""
    if stop.is_set():
        return
    blocks = wav_blocks(path)
    try:
        # Validate the source before connecting to the microphone's transport.
        first = next(blocks, None)
        if first is None:
            return
        with ApoTransport(library, endpoint_token, local_test=local_test) as sender:
            pacer = _Pacer(stop)
            block = first
            while not stop.is_set():
                sender.write(block, gain() if callable(gain) else gain)
                if on_level is not None:
                    on_level(float(np.max(np.abs(block))) if block.size else 0.0)
                if pacer.wait(len(block)):
                    break
                block = next(blocks, None)
                if block is None:
                    # Let the last packet reach an audio-engine callback before stop.
                    stop.wait(0.03)
                    break
    finally:
        blocks.close()


def play_process(library: Path, endpoint_token: str, pid: int, stop: threading.Event,
                 *, gain=0.5, local_test=False, on_level=None):
    """Send only the selected app's audio; never fall back to all system audio."""
    if stop.is_set():
        return
    if requires_device_routing():
        raise audio.AudioError("Selected-app capture needs Windows 11. On Windows 10, use WAV playback with the APO.")
    if not pid or audio.ProcessAudioCapture is None:
        raise audio.AudioError("Choose a running app and install the process capture package.")
    queue = AudioBuffer(limit=4800)

    def received(data, _frames):
        size = len(data) - len(data) % 8
        queue.put(np.frombuffer(data[:size], dtype=np.float32).reshape(-1, 2))

    tap = audio.ProcessAudioCapture(pid, on_data=received)
    try:
        native = getattr(getattr(tap, "_backend", None), "_native", None)
        if not native or not native.is_process_specific():
            raise audio.AudioError("This app cannot be captured separately on this PC.")
        with ApoTransport(library, endpoint_token, local_test=local_test) as sender:
            tap.start()
            pacer = _Pacer(stop)
            while not stop.is_set():
                block = queue.take(FRAMES)
                sender.write(block, gain() if callable(gain) else gain)
                if on_level is not None:
                    on_level(float(np.max(np.abs(block))))
                if pacer.wait(FRAMES):
                    break
    finally:
        tap.stop()


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--token", required=True, help="Token from an existing APO attachment, not a device name")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--wav", type=Path)
    source.add_argument("--pid", type=int)
    parser.add_argument("--gain", type=float, default=0.5)
    parser.add_argument("--local-test", action="store_true", help="Standalone test host only")
    args = parser.parse_args()
    if not np.isfinite(args.gain) or not 0 <= args.gain <= 1:
        parser.error("gain must be between 0 and 1")
    stop = threading.Event()
    try:
        function = play_file if args.wav else play_process
        function(args.library, args.token, args.wav or args.pid, stop,
                 gain=args.gain, local_test=args.local_test)
    except KeyboardInterrupt:
        stop.set()
    except (OSError, ValueError, RuntimeError, audio.AudioError, wave.Error) as error:
        parser.exit(1, f"Music playback failed: {error}\n")


if __name__ == "__main__":
    main()
