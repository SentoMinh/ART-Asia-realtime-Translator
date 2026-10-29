import os
import sys
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QMessageBox

from ui import i18n, music_dialog
from ui.config import Settings


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated_tests(monkeypatch):
    old_lang = i18n.lang()
    i18n.set_lang("en")
    monkeypatch.setattr(music_dialog, "prototype_test_command", lambda: None)
    monkeypatch.setattr(music_dialog, "attachment_for", lambda _: None)
    monkeypatch.setattr(music_dialog.apo_install, "registered_microphone", lambda: "")
    monkeypatch.setattr(music_dialog, "running_apps", lambda: [])
    monkeypatch.setattr(music_dialog, "MicrophoneStatus", lambda: SimpleNamespace(microphone="", refresh=lambda: None))
    yield
    i18n.set_lang(old_lang)


def test_no_driver_prompt_and_no_live_playback(app, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a: pytest.fail("No driver prompt"))
    dialog = music_dialog.MusicDialog(Settings(mic_device="Microphone (HyperX QuadCast)"))
    dialog.show()
    QTest.qWait(30)
    assert dialog.mic_note.text() == "Microphone (HyperX QuadCast)"
    assert not dialog.play_button.isEnabled()
    assert dialog.result.isHidden()
    assert not any("driver" in button.text().lower() for button in dialog.findChildren(QPushButton))
    dialog.settings.mic_device = "Other microphone"
    dialog.refresh()
    assert dialog.mic_note.text() == "Other microphone"
    dialog.close()


class Player:
    busy = active = False
    source_peak = 0.0
    gain = .5
    error = ""
    microphone = ""
    def start(self, kind, source, microphone):
        self.args = kind, source, microphone
        self.microphone = microphone
        self.busy = self.active = True
    def stop(self): self.busy = self.active = False
    def close(self): self.stop()


def test_mismatched_vrchat_microphone_warning_clears_after_selection_matches(ready_dialog):
    dialog = ready_dialog
    dialog._vrchat_microphone.microphone = "Virtual Desktop Audio"
    dialog.poll()
    assert not dialog.route_warning.isHidden()
    assert "Virtual Desktop Audio" in dialog.route_warning.text()
    dialog.settings.mic_device = "Virtual Desktop Audio"
    dialog.poll()
    assert dialog.route_warning.isHidden()
    dialog.settings.mic_device = "HyperX"
    dialog._vrchat_microphone.microphone = ""
    dialog.poll()
    assert dialog.route_warning.isHidden()


@pytest.fixture
def ready_dialog(app, monkeypatch):
    monkeypatch.setattr(music_dialog, "attachment_for", lambda _: {"phase": "validated"})
    monkeypatch.setattr(music_dialog, "requires_device_routing", lambda: False)
    monkeypatch.setattr(music_dialog, "running_apps", lambda: [(123, "Music player")])
    monkeypatch.setattr(music_dialog, "ApoPlayer", Player)
    dialog = music_dialog.MusicDialog(Settings(mic_device="HyperX"))
    dialog.apps.setCurrentIndex(dialog.apps.findData(123))
    yield dialog
    dialog.close()


@pytest.mark.parametrize("exit_code", [0, 1])
def test_play_checks_mixer_and_only_starts_after_success(ready_dialog, monkeypatch, tmp_path, exit_code):
    monkeypatch.setattr(music_dialog, "prototype_test_command", lambda: (
        sys.executable, ["-c", f"print('fixture result'); raise SystemExit({exit_code})"], str(tmp_path)))
    dialog = ready_dialog
    dialog.play_button.click()
    assert not dialog.player.active
    assert dialog.play_button.toolTip() == "Stop music"
    for _ in range(100):
        QTest.qWait(20)
        if not dialog.test_running:
            break
    assert not dialog.test_running
    assert dialog.player.active == (exit_code == 0)
    if exit_code == 0:
        assert dialog.result.isHidden() and dialog.details.isHidden()
        dialog.play_button.click()
        assert not dialog.player.active
        assert dialog.play_button.toolTip() == "Start music"
    else:
        assert "failed" in dialog.result.text()
        assert "fixture result" in dialog.details.toPlainText()
        assert not dialog.details.isHidden()
    assert dialog.play_button.isEnabled()


def test_failed_launch_is_reported_and_can_retry(ready_dialog, monkeypatch, tmp_path):
    monkeypatch.setattr(music_dialog, "prototype_test_command", lambda: (str(tmp_path / "missing.exe"), [], str(tmp_path)))
    dialog = ready_dialog
    dialog.play_button.click()
    QTest.qWait(100)
    assert "Could not start" in dialog.result.text()
    assert not dialog._timeout.isActive()
    assert not dialog.player.active
    assert dialog.play_button.isEnabled()


@pytest.mark.parametrize("action", ["close", "stop", "timeout"])
def test_interrupted_check_never_starts_music(ready_dialog, monkeypatch, tmp_path, action):
    monkeypatch.setattr(music_dialog, "prototype_test_command", lambda: (
        sys.executable, ["-c", "import time; time.sleep(10)"], str(tmp_path)))
    dialog = ready_dialog
    dialog.play_button.click()
    QTest.qWait(50)
    assert dialog.test_running
    if action == "close":
        dialog.shutdown()
    elif action == "stop":
        dialog.play_button.click()
    else:
        dialog._test_timeout()
    for _ in range(100):
        QTest.qWait(10)
        if not dialog.test_running:
            break
    assert not dialog.test_running and not dialog.player.active
    assert not dialog._timeout.isActive()
    if action == "timeout":
        assert "timed out" in dialog.result.text()
    else:
        assert dialog.result.isHidden()


def test_main_window_reopens_dialog_without_legacy_router(app):
    from ui.backend import Backend
    from ui.main_window import MainWindow
    window = MainWindow(Backend(), Settings(), save=lambda _: None)
    window.open_music()
    original = window._music_dialog
    original.reject()
    window.open_music()
    assert window._music_dialog is original
    original.close()
    window.deleteLater()


@pytest.mark.parametrize("language", ["zh", "vi"])
def test_new_dialog_copy_is_translated(app, language):
    i18n.set_lang(language)
    dialog = music_dialog.MusicDialog(Settings())
    assert dialog.play_button.toolTip() != "Start music"
    assert dialog.install_button.text() != "Install microphone mixer…"
    dialog.close()


def test_live_check_path_without_standalone_host_and_runtime_errors(ready_dialog):
    dialog = ready_dialog
    dialog.play_button.click()
    dialog.poll()
    assert dialog.player.args == ("app", 123, "HyperX")
    assert dialog.result.isHidden()
    dialog.player.source_peak = .25
    dialog.poll()
    assert dialog.source_meter.value() > 0
    assert dialog.result.isHidden()
    dialog.player.error = "Microphone disconnected"
    dialog.player.busy = dialog.player.active = False
    dialog.poll()
    assert dialog.result.text() == "Microphone disconnected"
    assert dialog.play_button.toolTip() == "Start music"


def test_microphone_change_stops_playback(ready_dialog):
    dialog = ready_dialog
    dialog.play_button.click()
    dialog.settings.mic_device = "Other mic"
    dialog.poll()
    assert not dialog.player.active
    assert not dialog.play_button.isEnabled()
    assert "Microphone changed" in dialog.result.text()


def test_install_button_runs_setup_and_refreshes_attachment(app, monkeypatch, tmp_path):
    monkeypatch.setattr(music_dialog.apo_install, "setup_command", lambda _: (
        sys.executable, ["-c", 'import pathlib, sys; pathlib.Path(sys.argv[-1]).write_text(\'{"ok": true, "already_installed": true}\')']))
    dialog = music_dialog.MusicDialog(Settings(mic_device="HyperX"))
    assert not dialog.install_button.isHidden()
    monkeypatch.setattr(music_dialog, "attachment_for", lambda _: {"phase": "validated"})
    dialog.install_mixer()
    assert dialog.setup_running
    for _ in range(100):
        QTest.qWait(20)
        if not dialog.setup_running:
            break
    assert "already installed" in dialog.result.text()
    assert dialog.install_button.isHidden()
    assert not dialog.setup_running
    dialog.close()


def test_declining_setup_does_not_launch_installer(app, monkeypatch):
    monkeypatch.setattr(music_dialog.apo_install, "setup_command", lambda _: pytest.fail("No consent"))
    dialog = music_dialog.MusicDialog(Settings())
    dialog.offer_setup()
    prompt = dialog._setup_prompt
    button = next(b for b in prompt.buttons() if prompt.buttonRole(b) == QMessageBox.RejectRole)
    button.click()
    assert not dialog.setup_running
    dialog.close()


def test_other_attachment_offers_use_button_and_persists_choice(app, monkeypatch):
    from ui.backend import Backend
    from ui.main_window import MainWindow
    existing = "Microphone (Virtual Desktop Audio)"
    monkeypatch.setattr(music_dialog.apo_install, "registered_microphone", lambda: existing)
    monkeypatch.setattr(music_dialog.apo_install, "endpoint_for", lambda name: "endpoint")
    monkeypatch.setattr(music_dialog.apo_install, "setup_command", lambda _: pytest.fail("Must not install again"))
    monkeypatch.setattr(music_dialog, "attachment_for", lambda name: {"phase": "validated"} if name == existing else None)
    monkeypatch.setattr(music_dialog, "requires_device_routing", lambda: False)
    monkeypatch.setattr(music_dialog, "running_apps", lambda: [(123, "Music player")])
    saved = []
    window = MainWindow(Backend(), Settings(mic_device="HyperX"), save=lambda s: saved.append(s.mic_device))
    try:
        window.open_music()
        dialog = window._music_dialog
        assert existing in dialog.result.text()
        assert dialog.install_button.isHidden() and not dialog.use_installed_button.isHidden()
        assert not hasattr(dialog, "_setup_prompt")
        assert not dialog.play_button.isEnabled()
        dialog.use_installed_button.click()
        assert window.settings.mic_device == existing and saved[-1] == existing
        assert dialog.mic_note.text() == existing
        assert dialog.use_installed_button.isHidden() and dialog.install_button.isHidden()
        dialog.apps.setCurrentIndex(dialog.apps.findData(123))
        assert dialog.play_button.isEnabled()
    finally:
        window.close()


def test_use_existing_attachment_checks_endpoint_before_changing_selection(app, monkeypatch):
    monkeypatch.setattr(music_dialog.apo_install, "registered_microphone", lambda: "Disconnected headset")
    def unavailable(_):
        raise RuntimeError("Microphone is not active")
    monkeypatch.setattr(music_dialog.apo_install, "endpoint_for", unavailable)
    dialog = music_dialog.MusicDialog(Settings(mic_device="HyperX"))
    saved = []
    dialog.settings_changed.connect(lambda: saved.append(True))
    try:
        dialog.use_installed_button.click()
        assert dialog.settings.mic_device == "HyperX" and not saved
        assert "not active" in dialog.result.text()
    finally:
        dialog.shutdown()
        dialog.close()


def test_hidden_idle_dialog_stops_polling_until_shown_or_playing(ready_dialog):
    dialog = ready_dialog
    dialog.show()
    assert dialog._poll_timer.isActive() and dialog._route_timer.isActive()
    dialog.reject()
    assert not dialog._route_timer.isActive()
    dialog.poll()
    assert not dialog._poll_timer.isActive()
    dialog.show()
    assert dialog._poll_timer.isActive() and dialog._route_timer.isActive()
    dialog.play_button.click()
    dialog.reject()
    dialog.poll()
    assert dialog.player.active and dialog._poll_timer.isActive()
    assert not dialog._route_timer.isActive()
    dialog.shutdown()


def test_close_or_reject_keeps_music_active(ready_dialog):
    dialog = ready_dialog
    dialog.play_button.click()
    dialog.poll()
    assert dialog.player.active
    dialog.reject()
    assert dialog.isHidden()
    assert dialog.player.active
    dialog.close()
    assert dialog.player.active
    dialog.shutdown()
    assert not dialog.player.active
