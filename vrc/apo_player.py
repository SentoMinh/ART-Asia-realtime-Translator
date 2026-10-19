"""Playback controls for a validated installation on the selected microphone."""
from __future__ import annotations

import hashlib
import ctypes
from pathlib import Path
import threading
import time

from . import apo_music, apo_setup
from .apo_transport import probe


def attachment_for(microphone):
    state = apo_setup.load_state()
    if not state or state.get("phase") != "validated" or state.get("microphone") != microphone:
        return None
    for name in apo_setup.NAMES:
        path = Path(state["directory"]) / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != state.get("hashes", {}).get(name):
            raise RuntimeError("The installed microphone mixer changed. Run setup again before playing music.")
    return state


class ApoPlayer:
    def __init__(self):
        self.gain = .5
        self.active = False
        self.error = ""
        self.microphone = ""
        self._signal = (0.0, 0.0)
        self._stop = threading.Event()
        self._worker = None

    @property
    def busy(self):
        return self._worker is not None and self._worker.is_alive()

    @property
    def source_peak(self):
        peak, timestamp = self._signal
        return peak if self.active and time.monotonic() - timestamp < .5 else 0.0

    def _source_level(self, peak):
        # Hold peaks briefly so the GUI can show short packets between polls.
        previous, timestamp = self._signal
        now = time.monotonic()
        if peak >= previous or now - timestamp >= .25:
            self._signal = (peak, now)

    def start(self, kind, source, microphone):
        if self.busy:
            raise RuntimeError("Music is still stopping. Try again in a moment.")
        if kind not in ("wav", "app"):
            raise ValueError("Choose a WAV file or running app.")
        state = attachment_for(microphone)
        if not state:
            raise RuntimeError("The mixer is not installed and validated on this microphone.")
        self.error = ""
        self._signal = (0.0, 0.0)
        self.microphone = microphone
        self._stop.clear()

        def work():
            initialized = False
            try:
                result = ctypes.windll.ole32.CoInitializeEx(None, 0)
                if result < 0:
                    raise RuntimeError(f"Could not initialize Windows audio on the music thread (0x{result & 0xffffffff:08x}).")
                initialized = True
                library = Path(state["directory"]) / "VrctApoProducer.dll"
                with apo_setup.open_capture(microphone) as capture:
                    until = time.monotonic() + 4
                    while not self._stop.is_set() and probe(library, state["token"]) != 2:
                        if time.monotonic() >= until:
                            raise RuntimeError("Windows has not activated the microphone mixer. Reopen your audio apps and try again.")
                        self._stop.wait(.05)
                    if self._stop.is_set():
                        return
                    self.active = True
                    last_check = time.monotonic()
                    def current_gain():
                        nonlocal last_check
                        now = time.monotonic()
                        if now - last_check >= .5:
                            if not capture.active or probe(library, state["token"]) != 2:
                                raise RuntimeError("The microphone mixer disconnected. Check your microphone and start again.")
                            last_check = now
                        return self.gain
                    function = apo_music.play_file if kind == "wav" else apo_music.play_process
                    function(library, state["token"], source, self._stop,
                             gain=current_gain, on_level=self._source_level)
            except Exception as error:
                self.error = str(error) or type(error).__name__
            finally:
                self.active = False
                if initialized:
                    ctypes.windll.ole32.CoUninitialize()

        self._worker = threading.Thread(target=work, name="apo-music", daemon=True)
        self._worker.start()

    def stop(self):
        self._stop.set()

    def close(self):
        self.stop()
        if self._worker:
            self._worker.join(timeout=1)
