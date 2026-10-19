import threading
from types import SimpleNamespace
import wave

import numpy as np
import pytest

from vrc import apo_music as music


def wav_file(tmp_path, *, rate=44100, channels=1, width=2):
    path = tmp_path / "music.wav"
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(width)
        output.setframerate(rate)
        output.writeframes(np.full((rate // 10, channels), 8192, dtype="<i2").tobytes())
    return path


def test_wav_stream_resamples_and_duplicates_mono(tmp_path):
    blocks = list(music.wav_blocks(wav_file(tmp_path)))
    assert all(block.dtype == np.float32 and block.shape[1] == 2 and len(block) <= 480 for block in blocks)
    samples = np.concatenate(blocks)
    assert len(samples) == 4800
    np.testing.assert_array_equal(samples[:, 0], samples[:, 1])
    np.testing.assert_allclose(samples[100:-100], 0.25, atol=0.001)


def test_invalid_wave_never_opens_transport(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(music, "ApoTransport", lambda *a, **kw: opened.append(True))
    with pytest.raises(ValueError, match="16-bit PCM"):
        music.play_file(None, "", wav_file(tmp_path, width=1), threading.Event())
    assert opened == []


def test_cancellation_closes_on_same_thread(tmp_path, monkeypatch):
    stop = threading.Event()
    actions = []

    class Sender:
        def __init__(self, *a, **kw):
            actions.append(("open", threading.get_ident()))
        def __enter__(self): return self
        def write(self, data, gain):
            actions.append(("write", threading.get_ident()))
            assert gain == .3
            stop.set()
        def __exit__(self, *a): actions.append(("close", threading.get_ident()))

    monkeypatch.setattr(music, "ApoTransport", Sender)
    music.play_file(None, "", wav_file(tmp_path), stop, gain=.3)
    assert [name for name, _ in actions] == ["open", "write", "close"]
    assert len({owner for _, owner in actions}) == 1


def test_process_fallback_is_rejected_and_capture_cleaned_up(monkeypatch):
    stopped = []
    monkeypatch.setattr(music, "requires_device_routing", lambda: False)
    tap = SimpleNamespace(_backend=SimpleNamespace(_native=SimpleNamespace(is_process_specific=lambda: False)),
                          stop=lambda: stopped.append(True))
    monkeypatch.setattr(music.audio, "ProcessAudioCapture", lambda *a, **kw: tap)
    with pytest.raises(music.audio.AudioError, match="separately"):
        music.play_process(None, "", 123, threading.Event())
    assert stopped == [True]


def test_windows10_does_not_capture_other_apps(monkeypatch):
    monkeypatch.setattr(music, "requires_device_routing", lambda: True)
    monkeypatch.setattr(music.audio, "ProcessAudioCapture", lambda *a, **kw: pytest.fail("Must not open capture"))
    with pytest.raises(music.audio.AudioError, match="WAV playback"):
        music.play_process(None, "", 123, threading.Event())


def test_capture_error_closes_sender_and_tap(monkeypatch):
    actions = []
    class Sender:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): actions.append("sender closed")
        def write(self, *a): raise RuntimeError("transport failure")
    monkeypatch.setattr(music, "ApoTransport", Sender)
    monkeypatch.setattr(music, "requires_device_routing", lambda: False)
    tap = SimpleNamespace(_backend=SimpleNamespace(_native=SimpleNamespace(is_process_specific=lambda: True)),
                          start=lambda: actions.append("started"), stop=lambda: actions.append("stopped"))
    monkeypatch.setattr(music.audio, "ProcessAudioCapture", lambda *a, **kw: tap)
    with pytest.raises(RuntimeError, match="transport failure"):
        music.play_process(None, "", 123, threading.Event())
    assert actions == ["started", "sender closed", "stopped"]


def test_process_meter_reports_audio_then_silence(monkeypatch):
    stop = threading.Event()
    levels = []
    packets = []
    callbacks = []
    class Sender:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def write(self, data, gain): packets.append(data.copy())
    def capture(pid, on_data):
        return SimpleNamespace(
            _backend=SimpleNamespace(_native=SimpleNamespace(is_process_specific=lambda: True)),
            start=lambda: on_data(np.full((480, 2), .25, dtype=np.float32).tobytes(), 480),
            stop=lambda: callbacks.append("closed"))
    def measured(peak):
        levels.append(peak)
        if len(levels) == 2:
            stop.set()
    monkeypatch.setattr(music, "requires_device_routing", lambda: False)
    monkeypatch.setattr(music, "ApoTransport", Sender)
    monkeypatch.setattr(music.audio, "ProcessAudioCapture", capture)
    music.play_process(None, "", 123, stop, on_level=measured)
    assert levels == [.25, 0.0]
    assert len(packets) == 2 and not packets[1].any()
    assert callbacks == ["closed"]
