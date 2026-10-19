"""Mix one application's audio and voice for our virtual microphone driver."""
from __future__ import annotations

import ctypes
import os
import sys
import threading
from collections import deque
from ctypes import wintypes

import numpy as np
import soxr

from . import audio

RATE = 48000
VIRTUAL_OUTPUT = "VRChat Translator Mix"
VIRTUAL_MIC = "VRChat Translator Microphone"
MUSIC_INPUT = "VRChat Translator Music"
MIN_WINDOWS_BUILD = 19045  # Windows 10 22H2


def requires_device_routing() -> bool:
    """Windows 10 desktop lacks the process-loopback API used on Windows 11."""
    return sys.platform == "win32" and sys.getwindowsversion().build < 22000


class MusicInputAudio(audio.OutputAudio):
    """Capture only our dedicated music endpoint, preserving stereo and resampling."""

    def __init__(self, on_samples, on_error):
        name = next((name for name in audio.output_devices() if MUSIC_INPUT in name), None)
        if name is None:
            raise audio.AudioError("The VRChat Translator Music device is missing. Install the updated audio driver.")
        self._on_samples, self._on_error = on_samples, on_error
        super().__init__(name)
        try:
            if self.channels != 2:
                raise audio.AudioError("The VRChat Translator Music device must use stereo audio.")
            self._converter = soxr.ResampleStream(self.rate, RATE, 2, dtype="float32")
        except Exception:
            self.stop()
            raise

    def _callback(self, data, _frames, _time, _status):
        try:
            samples = np.frombuffer(data, dtype=np.float32).reshape(-1, 2)
            self._on_samples(self._converter.resample_chunk(samples))
            return None, self._api.paContinue
        except Exception as error:
            self._on_error(str(error) or "The music input stopped.")
            return None, self._api.paAbort


def running_apps() -> list[tuple[int, str]]:
    """Visible desktop apps; process-tree capture includes browser audio subprocesses."""
    if sys.platform != "win32":
        return []
    user = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    found = {}

    @callback_type
    def visit(hwnd, _):
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        title = ctypes.create_unicode_buffer(512)
        user.GetWindowTextW(hwnd, title, len(title))
        if pid.value != os.getpid() and title.value and user.IsWindowVisible(hwnd):
            found.setdefault(pid.value, title.value)
        return True

    user.EnumWindows(visit, 0)
    return sorted(found.items(), key=lambda item: item[1].casefold())


def playback_devices() -> list[str]:
    if audio.sounddevice is None:
        return []
    try:
        return [d["name"] for _, d in _outputs() if VIRTUAL_OUTPUT in d["name"]]
    except Exception:
        return []


def _outputs():
    apis = audio.sounddevice.query_hostapis()
    return [(i, d) for i, d in enumerate(audio.sounddevice.query_devices())
            if d["max_output_channels"] > 0 and "WASAPI" in apis[d["hostapi"]]["name"]]


class AudioBuffer:
    """Bounded stereo queue; discard old audio rather than building a playback delay."""
    def __init__(self, limit=RATE // 4):
        self.limit = limit
        self.chunks = deque()
        self.frames = 0
        self.lock = threading.Lock()

    def put(self, data):
        if not len(data):
            return
        with self.lock:
            data = np.asarray(data[-self.limit:], dtype=np.float32).copy()
            self.chunks.append(data)
            self.frames += len(data)
            while self.frames > self.limit:
                self.frames -= len(self.chunks.popleft())

    def take(self, count):
        result = np.zeros((count, 2), dtype=np.float32)
        with self.lock:
            offset = 0
            while self.chunks and offset < count:
                chunk = self.chunks.popleft()
                used = min(len(chunk), count - offset)
                result[offset:offset + used] = chunk[:used]
                if used < len(chunk):
                    self.chunks.appendleft(chunk[used:])
                offset += used
                self.frames -= used
        return result


class MusicRouter:
    def __init__(self):
        self.music_gain = 0.5
        self.active = False
        self.error = ""
        self.pid = 0
        self.output = ""
        self.mic_device = ""
        self.include_mic = False
        self._tap = self._mic = self._stream = None
        self._lock = threading.RLock()
        self._music = AudioBuffer()
        self._voice = AudioBuffer()

    def start(self, pid, output, mic_device="", include_mic=True):
        with self._lock:
            self.stop()
            self.error = ""
            self._music, self._voice = AudioBuffer(), AudioBuffer()
            try:
                if sys.platform != "win32" or sys.getwindowsversion().build < MIN_WINDOWS_BUILD:
                    raise audio.AudioError("Music routing requires Windows 10 22H2 or Windows 11 (64-bit).")
                device_routing = requires_device_routing()
                if audio.sounddevice is None or (not device_routing and audio.ProcessAudioCapture is None):
                    raise audio.AudioError("The audio packages are not installed.")
                match = next(((i, d) for i, d in _outputs()
                              if d["name"] == output and VIRTUAL_OUTPUT in d["name"]), None)
                if not match:
                    raise audio.AudioError("The VRChat Translator virtual microphone driver is not installed.")
                if include_mic:
                    source = audio.sounddevice.query_devices(mic_device or None, "input")
                    if VIRTUAL_MIC in source["name"]:
                        raise audio.AudioError("Choose your physical microphone as the voice input to avoid feedback.")
                if device_routing:
                    self._tap = MusicInputAudio(self._music.put, lambda error: setattr(self, "error", error))
                else:
                    if not pid:
                        raise audio.AudioError("Choose a running music app first.")
                    self._tap = audio.ProcessAudioCapture(pid, on_data=self._app_audio)
                    native = getattr(getattr(self._tap, "_backend", None), "_native", None)
                    if not native or not native.is_process_specific():
                        raise audio.AudioError("This app cannot be captured separately on this PC.")
                channels = min(2, int(match[1]["max_output_channels"]))
                self._stream = audio.sounddevice.OutputStream(
                    device=match[0], samplerate=RATE, channels=channels, dtype="float32",
                    blocksize=960, callback=self._play, finished_callback=self._finished)
                if include_mic:
                    self._mic = audio.MicAudio(mic_device)
                    converter = soxr.ResampleStream(self._mic.rate, RATE, 1, dtype="float32")
                    self._mic._on_audio = lambda samples, rate: self._voice.put(
                        np.repeat(converter.resample_chunk(samples)[:, None], 2, axis=1))
                self.pid, self.output = pid, output
                self.mic_device, self.include_mic = mic_device, include_mic
                self._tap.start()
                if self._mic:
                    self._mic.start()
                self.active = True
                self._stream.start()
            except Exception:
                self.stop()
                raise

    def _app_audio(self, data, _frames):
        size = len(data) - len(data) % 8
        self._music.put(np.frombuffer(data[:size], dtype=np.float32).reshape(-1, 2))

    def _play(self, out, frames, _time, _status):
        try:
            mixed = self._music.take(frames) * self.music_gain + self._voice.take(frames)
            np.clip(mixed, -1, 1, out=mixed)
            out[:] = mixed if out.shape[1] == 2 else mixed.mean(axis=1, keepdims=True)
        except Exception as error:
            out.fill(0)
            self.error = str(error)
            raise audio.sounddevice.CallbackAbort

    def _finished(self):
        if self.active:
            self.error = self.error or "The music output stopped. Check the device and start again."
            self.active = False

    def stop(self):
        with self._lock:
            self.active = False
            for name in ("_tap", "_mic", "_stream"):
                resource = getattr(self, name)
                setattr(self, name, None)
                if resource is not None:
                    try:
                        resource.stop()
                    except Exception:
                        pass
                    finally:
                        if name == "_stream":
                            try:
                                resource.close()
                            except Exception:
                                pass
