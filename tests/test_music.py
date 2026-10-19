import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from ui.config import Settings
from ui.backend import Backend, Status
from ui.main_window import MainWindow
from vrc import music


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_status_keeps_light_and_details_but_shortens_text(app):
    window = MainWindow(Backend(), Settings(), save=lambda _: None)
    window.show_status(Status("error", "VRChat not found", "Start VRChat."))
    assert window.status.text() == "VRChat"
    assert window.status.toolTip() == "Start VRChat."
    assert "VRChat not found" in window.status.accessibleName()
    assert window.music_button is not None
    window.deleteLater()


def test_music_buffer_bounds_and_underflow():
    buffer = music.AudioBuffer(limit=4)
    buffer.put(np.ones((3, 2)))
    buffer.put(np.full((3, 2), .5))
    buffer.put(np.empty((0, 2)))
    assert buffer.frames == 3 and len(buffer.chunks) == 1
    np.testing.assert_allclose(buffer.take(4), [[.5,.5],[.5,.5],[.5,.5],[0,0]])
    assert buffer.frames == 0


def test_music_mixes_voice_preserves_stereo_and_clips():
    router = music.MusicRouter()
    router.music_gain = .5
    router._music.put(np.array([[.8, -.8], [1, 1]], dtype=np.float32))
    router._voice.put(np.full((2, 2), .8))
    out = np.empty((3, 2), dtype=np.float32)
    router._play(out, 3, None, None)
    np.testing.assert_allclose(out, [[1,.4],[1,1],[0,0]], atol=1e-6)


def test_system_wide_fallback_is_rejected_and_closed(monkeypatch):
    monkeypatch.setattr(music.sys, "getwindowsversion", lambda: SimpleNamespace(build=22631))
    monkeypatch.setattr(music, "_outputs", lambda: [(4, dict(name=music.VIRTUAL_OUTPUT, max_output_channels=2))])
    stopped = []
    tap = SimpleNamespace(_backend=SimpleNamespace(_native=SimpleNamespace(is_process_specific=lambda: False)),
                          stop=lambda: stopped.append(True))
    monkeypatch.setattr(music.audio, "ProcessAudioCapture", lambda *a, **kw: tap)
    router = music.MusicRouter()
    with pytest.raises(music.audio.AudioError, match="separately"):
        router.start(100, music.VIRTUAL_OUTPUT, include_mic=False)
    assert stopped and not router.active and router._tap is None


def test_only_our_endpoint_is_offered_and_other_outputs_are_rejected(monkeypatch):
    monkeypatch.setattr(music.sys, "getwindowsversion", lambda: SimpleNamespace(build=22631))
    monkeypatch.setattr(music, "_outputs", lambda: [
        (1, dict(name="Speakers", max_output_channels=2)),
        (2, dict(name=music.VIRTUAL_OUTPUT, max_output_channels=2)),
        (3, dict(name="CABLE Input", max_output_channels=2)),
    ])
    assert music.playback_devices() == [music.VIRTUAL_OUTPUT]
    with pytest.raises(music.audio.AudioError, match="not installed"):
        music.MusicRouter().start(10, "Speakers", include_mic=False)


@pytest.mark.parametrize("selected", ["", music.VIRTUAL_MIC])
def test_virtual_microphone_feedback_is_rejected_including_windows_default(monkeypatch, selected):
    monkeypatch.setattr(music.sys, "getwindowsversion", lambda: SimpleNamespace(build=22631))
    monkeypatch.setattr(music, "_outputs", lambda: [(2, dict(name=music.VIRTUAL_OUTPUT, max_output_channels=2))])
    monkeypatch.setattr(music.audio.sounddevice, "query_devices", lambda *a: {"name": music.VIRTUAL_MIC})
    with pytest.raises(music.audio.AudioError, match="feedback"):
        music.MusicRouter().start(10, music.VIRTUAL_OUTPUT, selected, True)


def test_windows10_uses_dedicated_input_without_process_capture(monkeypatch):
    monkeypatch.setattr(music.sys, "getwindowsversion", lambda: SimpleNamespace(build=19045))
    monkeypatch.setattr(music.audio, "ProcessAudioCapture", None)
    monkeypatch.setattr(music, "_outputs", lambda: [(2, dict(name=music.VIRTUAL_OUTPUT, max_output_channels=2))])
    events = []
    class Input:
        def __init__(self, on_samples, on_error):
            self.samples = on_samples
        def start(self):
            events.append("input start")
            self.samples(np.array([[.8, -.4]], dtype=np.float32))
        def stop(self): events.append("input stop")
    class Output:
        def __init__(self, **kwargs): self.callback = kwargs["callback"]
        def start(self):
            events.append("output start")
            self.out = np.zeros((1, 2), dtype=np.float32)
            self.callback(self.out, 1, None, None)
        def stop(self): events.append("output stop")
        def close(self): events.append("output close")
    monkeypatch.setattr(music, "MusicInputAudio", Input)
    monkeypatch.setattr(music.audio.sounddevice, "OutputStream", Output)
    router = music.MusicRouter()
    router.start(0, music.VIRTUAL_OUTPUT, include_mic=False)
    assert router.active
    np.testing.assert_allclose(router._stream.out, [[.4, -.2]])
    router.stop()
    assert events == ["input start", "output start", "input stop", "output stop", "output close"]


def test_music_input_never_falls_back_to_default_speakers(monkeypatch):
    monkeypatch.setattr(music.audio, "output_devices", lambda: ["Speakers [Loopback]", music.VIRTUAL_OUTPUT + " [Loopback]"])
    with pytest.raises(music.audio.AudioError, match="Music device is missing"):
        music.MusicInputAudio(lambda _: None, lambda _: None)


def test_music_input_preserves_stereo_and_reports_capture_errors(monkeypatch):
    chosen, received, errors = [], [], []
    name = music.MUSIC_INPUT + " [Loopback]"
    monkeypatch.setattr(music.audio, "output_devices", lambda: ["Speakers [Loopback]", name])
    def init(self, device):
        chosen.append(device)
        self.rate, self.channels = 48000, 2
        self._api = SimpleNamespace(paContinue=0, paAbort=2)
    monkeypatch.setattr(music.audio.OutputAudio, "__init__", init)
    capture = music.MusicInputAudio(received.append, errors.append)
    samples = np.tile(np.array([[.3, -.7]], dtype=np.float32), (4096, 1))
    assert capture._callback(samples.tobytes(), len(samples), None, None) == (None, 0)
    assert chosen == [name]
    np.testing.assert_allclose(received[0], samples)
    assert capture._callback(b"bad", 0, None, None) == (None, 2)
    assert errors


def test_windows_before_22h2_is_rejected_before_opening_audio(monkeypatch):
    monkeypatch.setattr(music.sys, "getwindowsversion", lambda: SimpleNamespace(build=19044))
    monkeypatch.setattr(music, "_outputs", lambda: pytest.fail("Must reject before opening audio"))
    with pytest.raises(music.audio.AudioError, match="22H2"):
        music.MusicRouter().start(0, music.VIRTUAL_OUTPUT)
