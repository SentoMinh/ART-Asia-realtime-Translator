"""Live sound: VRChat, a chosen Windows playback device, and the microphone.

Both hand out mono float32 chunks with their sample rate, for the speech engine, and keep the
loudest level since it was last asked, for the level bars. Uses proc-tap for VRChat
(system audio fallback on Windows 10), PyAudioWPatch for output devices, and sounddevice
for the microphone.
"""
from __future__ import annotations

import math

import numpy as np

try:
    from proctap import ProcessAudioCapture
except ImportError:
    ProcessAudioCapture = None
try:
    import sounddevice
except (ImportError, OSError):   # OSError: the PortAudio library is missing
    sounddevice = None

GAME_RATE = 48000      # proc-tap always gives 48 kHz stereo float32
FLOOR_DB = -60.0       # this quiet or quieter shows as an empty bar


class AudioError(Exception):
    """Sound can't be captured; the message says why in plain words."""


def to_level(samples: np.ndarray) -> float:
    """Loudness as 0.0 – 1.0 for a level bar (FLOOR_DB … 0 dB)."""
    if samples.size == 0:
        return 0.0
    rms = math.sqrt(float(np.mean(np.square(samples, dtype=np.float64))))
    if rms <= 0:
        return 0.0
    return min(max(1 - 20 * math.log10(rms) / FLOOR_DB, 0.0), 1.0)


def stereo_to_mono(data: bytes) -> np.ndarray:
    samples = np.frombuffer(data[:len(data) - len(data) % 8], dtype=np.float32)
    return samples.reshape(-1, 2).mean(axis=1)


class _Source:
    def __init__(self, on_audio=None):
        self._on_audio = on_audio     # on_audio(mono float32 array, sample rate), on an audio thread
        self._peak = 0.0

    def level(self) -> float:
        """The loudest level since the last call."""
        peak, self._peak = self._peak, 0.0
        return peak

    def _heard(self, mono: np.ndarray, rate: int) -> None:
        self._peak = max(self._peak, to_level(mono))
        if self._on_audio is not None:
            self._on_audio(mono, rate)


class GameAudio(_Source):
    """Only the sound that the process `pid` (VRChat) plays."""

    def __init__(self, pid: int, on_audio=None):
        super().__init__(on_audio)
        if ProcessAudioCapture is None:
            raise AudioError("the proc-tap package is not installed")
        try:
            self._tap = ProcessAudioCapture(pid, on_data=self._on_data)
        except Exception as error:
            raise AudioError(str(error) or type(error).__name__) from error

    def _on_data(self, data: bytes, _frames: int) -> None:
        self._heard(stereo_to_mono(data), GAME_RATE)

    def start(self) -> None:
        try:
            self._tap.start()
        except Exception as error:
            raise AudioError(str(error) or type(error).__name__) from error

    def stop(self) -> None:
        self._tap.stop()


def _wasapi_inputs() -> list[tuple[int, dict]]:
    """Microphones as Windows' modern sound system lists them (full names, no duplicates)."""
    if sounddevice is None:
        return []
    apis = sounddevice.query_hostapis()
    wasapi = next((i for i, api in enumerate(apis) if "WASAPI" in api["name"]), None)
    return [(index, device) for index, device in enumerate(sounddevice.query_devices())
            if device["max_input_channels"] > 0 and (wasapi is None or device["hostapi"] == wasapi)]


def input_devices() -> list[str]:
    try:
        return [device["name"] for _, device in _wasapi_inputs()]
    except Exception:
        return []


class MicAudio(_Source):
    """A microphone by name; "" is the Windows default one."""

    def __init__(self, device: str = "", on_audio=None):
        super().__init__(on_audio)
        if sounddevice is None:
            raise AudioError("the sounddevice package is not installed")
        index, rate = None, None
        if device:
            match = next(((i, d) for i, d in _wasapi_inputs() if d["name"] == device), None)
            if match is None:
                raise AudioError(f"the microphone “{device}” was not found")
            index, rate = match[0], int(match[1]["default_samplerate"])
        try:
            if rate is None:
                rate = int(sounddevice.query_devices(kind="input")["default_samplerate"])
            self.rate = rate
            self._stream = sounddevice.InputStream(device=index, channels=1, samplerate=rate,
                                                   dtype="float32", callback=self._callback)
        except Exception as error:
            raise AudioError(str(error) or type(error).__name__) from error

    def _callback(self, data, _frames, _time, _status) -> None:
        self._heard(data[:, 0].copy(), self.rate)

    def start(self) -> None:
        try:
            self._stream.start()
        except Exception as error:
            raise AudioError(str(error) or type(error).__name__) from error

    def stop(self) -> None:
        self._stream.stop()
        self._stream.close()


def _output_api():
    try:
        import pyaudiowpatch
        return pyaudiowpatch
    except (ImportError, OSError) as error:
        raise AudioError("output capture needs the PyAudioWPatch package") from error


def output_devices() -> list[str]:
    """Playback endpoints that Windows can record using WASAPI loopback."""
    try:
        with _output_api().PyAudio() as manager:
            return list(dict.fromkeys(device["name"] for device in
                                      manager.get_loopback_device_info_generator()))
    except Exception:
        return []


class OutputAudio(_Source):
    """All sound played through one output device, selected by its full name."""

    def __init__(self, device: str, on_audio=None):
        super().__init__(on_audio)
        self._api = _output_api()
        self._manager = self._api.PyAudio()
        self._stream = None
        try:
            match = next((d for d in self._manager.get_loopback_device_info_generator()
                          if d["name"] == device), None)
            if match is None:
                raise AudioError(f"the output device “{device}” was not found")
            self.rate = int(match["defaultSampleRate"])
            self.channels = int(match["maxInputChannels"])
            self._stream = self._manager.open(
                format=self._api.paFloat32, channels=self.channels, rate=self.rate,
                input=True, input_device_index=match["index"], frames_per_buffer=960,
                stream_callback=self._callback, start=False)
        except Exception as error:
            self.stop()
            raise AudioError(str(error) or type(error).__name__) from error

    def _callback(self, data, _frames, _time, _status):
        samples = np.frombuffer(data, dtype=np.float32)
        mono = samples.reshape(-1, self.channels).mean(axis=1)
        self._heard(mono, self.rate)
        return None, self._api.paContinue

    def start(self) -> None:
        try:
            self._stream.start_stream()
        except Exception as error:
            self.stop()
            raise AudioError(str(error) or type(error).__name__) from error

    def stop(self) -> None:
        stream, self._stream = self._stream, None
        manager, self._manager = self._manager, None
        try:
            if stream is not None:
                stream.close()
        finally:
            if manager is not None:
                manager.terminate()
