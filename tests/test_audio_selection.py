import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from ui import config, main_window
from ui.backend import Backend
from ui.live_backend import LiveBackend
from vrc import audio
from vrc.chatbox import VRChatState


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_toolbar_menus_save_choices_and_keep_mute_state(app, monkeypatch, tmp_path):
    monkeypatch.setattr(main_window, "input_devices", lambda: ["USB mic"])
    monkeypatch.setattr(main_window, "output_devices", lambda: ["Headphones [Loopback]", "Speakers [Loopback]"])
    path = tmp_path / "ui.json"
    backend = Backend()
    # The working tree also contains pending signals used by MainWindow.
    window = main_window.MainWindow(backend, config.Settings(mic_on=False), save=lambda s: config.save(s, path))
    for button, setting in ((window.mic_device_button, "mic_device"),
                            (window.speaker_device_button, "speaker_device")):
        menu = button.menu()
        window._fill_audio_menu(menu, setting)
        assert menu.actions()[0].text() == ("Windows default" if setting == "mic_device" else "VRChat")
        menu.actions()[1].trigger()
    saved = config.load(path)
    assert saved.mic_device == "USB mic"
    assert saved.speaker_device == "Headphones [Loopback]"
    assert not saved.mic_on
    monkeypatch.setattr(main_window, "output_devices", lambda: [])
    window._fill_audio_menu(window.speaker_device_button.menu(), "speaker_device")
    missing = window.speaker_device_button.menu().actions()[-1]
    assert missing.isChecked() and not missing.isEnabled()
    window.speaker_device_button.menu().actions()[0].trigger()
    assert window.settings.speaker_device == ""
    window.deleteLater()


class Source:
    def __init__(self, target, on_audio):
        self.target, self.on_audio = target, on_audio
        self.stopped = False
    def start(self): pass
    def stop(self): self.stopped = True
    def level(self): return 0


def test_output_capture_does_not_need_vrchat_and_switches_cleanly(app):
    backend = LiveBackend(game_audio=Source, mic_audio=Source, output_audio=Source, threaded=False)
    backend.settings = config.Settings(mic_on=False, speaker_device="Speakers")
    backend.state = VRChatState()
    received = []
    backend.on_game_audio = lambda data, rate: received.append(rate)
    backend._sync_audio()
    first = backend._game
    assert first.target == "Speakers"
    first.on_audio(np.zeros(5), 48000)
    assert received == [48000]
    backend.settings.speaker_device = "Headphones"
    backend._sync_audio()
    assert first.stopped and backend._game.target == "Headphones"
    second = backend._game
    backend.settings.speaker_device = ""
    backend._sync_audio()
    assert second.stopped and backend._game is None
    backend.state = VRChatState(running=True, pid=123, listening=True)
    backend._sync_audio()
    game = backend._game
    assert game.target == 123
    backend.settings.subtitles_on = False
    backend._sync_audio()
    assert game.stopped and backend._game is None


def test_output_stream_format_and_cleanup(monkeypatch):
    opened = {}
    events = []
    stream = SimpleNamespace(start_stream=lambda: events.append("start"), close=lambda: events.append("close"))
    class Manager:
        def get_loopback_device_info_generator(self):
            return iter([dict(name="Speakers", index=42, defaultSampleRate=44100, maxInputChannels=2)])
        def open(self, **kwargs):
            opened.update(kwargs)
            return stream
        def terminate(self): events.append("terminate")
    monkeypatch.setattr(audio, "_output_api", lambda: SimpleNamespace(PyAudio=Manager, paFloat32=1, paContinue=0))
    received = []
    capture = audio.OutputAudio("Speakers", lambda data, rate: received.append((data, rate)))
    assert opened["input_device_index"] == 42 and opened["rate"] == 44100
    capture.start()
    capture._callback(np.array([1, 0, .5, .5], dtype=np.float32).tobytes(), 2, None, None)
    np.testing.assert_allclose(received[0][0], [.5, .5])
    assert received[0][1] == 44100
    capture.stop()
    capture.stop()
    assert events == ["start", "close", "terminate"]
    with pytest.raises(audio.AudioError, match="not found"):
        audio.OutputAudio("Unplugged")
    assert events[-1] == "terminate"
