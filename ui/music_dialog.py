"""Playback through a validated microphone mixer, plus an isolated native test."""
from __future__ import annotations

from pathlib import Path
import math
import json
import sys
import tempfile

from PySide6.QtCore import QProcess, QTimer, Qt, Signal
from PySide6.QtWidgets import (QDialog, QFormLayout, QHBoxLayout, QLabel, QComboBox,
                               QSlider, QPlainTextEdit, QPushButton, QVBoxLayout, QProgressBar, QMessageBox, QStyle, QToolButton)

from vrc.apo_player import ApoPlayer, attachment_for
from vrc import apo_install
from vrc.microphone_status import MicrophoneStatus
from vrc.music import running_apps, requires_device_routing
from .i18n import tr
from . import theme


def prototype_test_command():
    """Only source checkouts have the standalone test host; never use a shipped APO."""
    if getattr(sys, "frozen", False):
        return None
    root = Path(__file__).resolve().parents[1]
    builds = sorted((root / ".tools").glob("apo-prototype*"),
                    key=lambda path: path.stat().st_mtime, reverse=True)
    for build in builds:
        files = [build / name for name in ("ApoTests.exe", "VrctMicApo-Test.dll", "VrctApoProducer.dll")]
        if all(path.is_file() for path in files):
            return str(files[0]), [str(path) for path in files[1:]], str(root)
    return None


class MusicDialog(QDialog):
    state_changed = Signal(bool)
    peak_changed = Signal(float)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.player = ApoPlayer()
        self._vrchat_microphone = MicrophoneStatus()
        self._attachment = None
        self._was_busy = False
        self._was_active = False
        self._test_command = None
        self._timed_out = False
        self._pending_play = None
        self._setup_prompted = False
        self._setup_output = ""
        self._setup_folder = None
        self._shutting_down = False
        self.setObjectName("settings")
        self.setWindowTitle(tr("Music to microphone"))
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        form = QFormLayout()
        self.mic_note = QLabel()
        self.mic_note.setTextFormat(Qt.PlainText)
        self.mic_note.setWordWrap(True)
        form.addRow(tr("Microphone input"), self.mic_note)
        self.apps = QComboBox()
        self.apps.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.apps.setMinimumContentsLength(24)
        source_row = QHBoxLayout()
        source_row.setContentsMargins(0, 0, 0, 0)
        source_row.setSpacing(6)
        source_row.addWidget(self.apps, 1)
        self.refresh_button = QToolButton()
        self.refresh_button.setIcon(theme.icon("reload"))
        self.refresh_button.setToolTip(tr("Refresh apps"))
        self.refresh_button.setAccessibleName(tr("Refresh apps"))
        self.refresh_button.setFixedSize(30, 28)
        self.refresh_button.clicked.connect(self.refresh)
        source_row.addWidget(self.refresh_button)
        form.addRow(tr("Music source"), source_row)
        self.apps.currentIndexChanged.connect(self._update_controls)
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(50)
        self.volume.valueChanged.connect(lambda value: setattr(self.player, "gain", value / 100))
        form.addRow(tr("Music volume"), self.volume)
        self.source_meter = QProgressBar()
        self.source_meter.setRange(0, 60)
        self.source_meter.setValue(0)
        self.source_meter.setTextVisible(False)
        self.source_meter.setAccessibleName(tr("Source audio"))
        self.source_meter.setToolTip(tr("Silent"))
        form.addRow(tr("Source audio"), self.source_meter)
        layout.addLayout(form)

        self.route_warning = QLabel()
        self.route_warning.setTextFormat(Qt.PlainText)
        self.route_warning.setWordWrap(True)
        self.route_warning.hide()
        layout.addWidget(self.route_warning)

        self.result = QLabel()
        self.result.setTextFormat(Qt.PlainText)
        self.result.setWordWrap(True)
        layout.addWidget(self.result)
        self.install_button = QPushButton(tr("Install microphone mixer…"))
        self.install_button.setIcon(self.style().standardIcon(QStyle.SP_VistaShield))
        self.install_button.clicked.connect(self.offer_setup)
        layout.addWidget(self.install_button)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumBlockCount(200)
        self.details.setMaximumHeight(150)
        self.details.setAccessibleName(tr("Mixer test output"))
        self.details.hide()
        layout.addWidget(self.details)

        row = QHBoxLayout()
        row.addStretch(1)
        self.play_button = QPushButton()
        self.play_button.setFixedSize(42, 32)
        self.play_button.clicked.connect(self.toggle_music)
        row.addWidget(self.play_button)
        layout.addLayout(row)

        self._process = QProcess(self)
        self._setup_process = QProcess(self)
        self._setup_process.setProcessChannelMode(QProcess.MergedChannels)
        self._setup_process.readyReadStandardOutput.connect(self._read_setup_output)
        self._setup_process.finished.connect(self._setup_finished)
        self._setup_process.errorOccurred.connect(self._setup_error)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._read_output)
        self._process.finished.connect(self._test_finished)
        self._process.errorOccurred.connect(self._test_error)
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.setInterval(30000)
        self._timeout.timeout.connect(self._test_timeout)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(50)
        self._poll_timer.timeout.connect(self.poll)
        self._poll_timer.start()
        self._route_timer = QTimer(self)
        self._route_timer.setInterval(2000)
        self._route_timer.timeout.connect(self._vrchat_microphone.refresh)
        self._route_timer.start()
        self._vrchat_microphone.refresh()
        self.refresh()

    @property
    def test_running(self):
        return self._process.state() != QProcess.NotRunning

    @property
    def setup_running(self):
        return self._setup_process.state() != QProcess.NotRunning

    def offer_setup(self):
        if self.setup_running or self.player.busy or self.test_running:
            return
        self._setup_prompted = True
        prompt = QMessageBox(self)
        prompt.setWindowTitle(tr("Microphone audio setup required"))
        prompt.setIcon(QMessageBox.Question)
        prompt.setText(tr("Install the microphone mixer to play music through your selected microphone?"))
        prompt.setInformativeText(tr("Windows will ask for administrator permission. Setup uses the local mixer files and briefly restarts Windows audio."))
        install = prompt.addButton(tr("Install"), QMessageBox.AcceptRole)
        install.setIcon(self.style().standardIcon(QStyle.SP_VistaShield))
        decline = prompt.addButton(tr("Not now"), QMessageBox.RejectRole)
        prompt.setDefaultButton(decline)
        prompt.setEscapeButton(decline)
        prompt.buttonClicked.connect(lambda button: self.install_mixer() if button is install else None)
        self._setup_prompt = prompt
        prompt.open()

    def install_mixer(self):
        if self.setup_running or self.player.busy or self.test_running:
            return
        try:
            program, arguments = apo_install.setup_command(self.settings.mic_device)
            self._setup_folder = tempfile.TemporaryDirectory(prefix="vrct-mixer-ui-")
            arguments += ["--report", str(Path(self._setup_folder.name) / "result.json")]
            self._setup_output = ""
            self._set_result(tr("Waiting for administrator approval and microphone setup…"))
            self._setup_process.setWorkingDirectory(str(Path(__file__).resolve().parents[1]))
            self._setup_process.start(program, arguments)
        except Exception as error:
            self._set_result(str(error))
        self._update_controls()

    def _read_setup_output(self):
        self._setup_output += bytes(self._setup_process.readAllStandardOutput()).decode("utf-8", errors="replace")

    def _setup_finished(self, code, status):
        self._read_setup_output()
        self.refresh()
        try:
            report = Path(self._setup_folder.name) / "result.json" if self._setup_folder else None
            outcome = json.loads(report.read_text(encoding="utf-8") if report and report.is_file()
                                 else self._setup_output.strip())
            if code != 0 or not outcome.get("ok"):
                raise RuntimeError(outcome.get("error", tr("Microphone setup failed.")))
            if not self._attachment:
                raise RuntimeError(tr("Microphone setup failed."))
            self._set_result(tr("Microphone mixer is already installed." if outcome.get("already_installed")
                                else "Microphone mixer installed. You can start music."))
        except Exception as error:
            self._set_result(str(error) if not isinstance(error, ValueError) else tr("Microphone setup failed."))
        finally:
            if self._setup_folder:
                self._setup_folder.cleanup()
                self._setup_folder = None
        self._update_controls()

    def _setup_error(self, error):
        if error == QProcess.FailedToStart:
            if self._setup_folder:
                self._setup_folder.cleanup()
                self._setup_folder = None
            self._set_result(self._setup_process.errorString())
            self._update_controls()

    def refresh(self):
        self.mic_note.setText(self.settings.mic_device or tr("Windows default"))
        setup_error = ""
        try:
            self._attachment = attachment_for(self.settings.mic_device)
        except Exception as error:
            self._attachment = None
            setup_error = str(error)
        if not self.player.busy:
            selected = self.apps.currentData()
            self.apps.blockSignals(True)
            self.apps.clear()
            self.apps.addItem(tr("Pick a running app…"), None)
            if not requires_device_routing():
                for pid, title in running_apps():
                    self.apps.addItem(f"{title} ({pid})", pid)
            self.apps.setCurrentIndex(max(0, self.apps.findData(selected)))
            self.apps.blockSignals(False)
        if not self.test_running:
            self._test_command = prototype_test_command()
            if not self.player.busy:
                self._set_result(setup_error or (tr("App audio capture currently requires Windows 11.")
                                                if requires_device_routing() else ""))
        self._update_controls()

    def _set_result(self, text):
        self.result.setText(text)
        self.result.setVisible(bool(text))

    def _update_controls(self, *_):
        if not hasattr(self, "_process"):
            return
        busy = self.player.busy or self.test_running or self.setup_running
        ready = self._attachment is not None and not requires_device_routing()
        chosen = self.apps.currentData()
        playing = self.player.busy or self.test_running
        self.play_button.setEnabled(not self.setup_running and (playing or (ready and bool(chosen))))
        self.play_button.setIcon(theme.icon("stop" if playing else "play", theme.ON_ACCENT))
        self.play_button.setToolTip(tr("Stop music" if playing else "Start music"))
        self.play_button.setAccessibleName(self.play_button.toolTip())
        self.refresh_button.setEnabled(not busy)
        self.volume.setEnabled(ready)
        self.apps.setEnabled(ready and not busy)
        self.install_button.setVisible(self._attachment is None)
        self.install_button.setEnabled(not busy)

    def toggle_music(self):
        if self.player.busy or self.test_running:
            self.stop_music()
        else:
            self.start_music()

    def start_music(self):
        if self.test_running or self.player.busy or self.setup_running:
            return
        source = self.apps.currentData()
        if not self._attachment or not source or requires_device_routing():
            return
        self._pending_play = (source, self.settings.mic_device)
        self._set_result("")
        self.details.clear()
        self.details.hide()
        self.run_test()

    def _launch_music(self):
        pending, self._pending_play = self._pending_play, None
        if pending is None:
            return
        source, microphone = pending
        if microphone != self.settings.mic_device:
            self._set_result(tr("Microphone changed. Start music again to use it."))
            self._update_controls()
            return
        try:
            # ApoPlayer also validates the installed files and live audio callback
            # before sending any audio, including in builds without the test host.
            self.player.start("app", source, microphone)
            self._was_busy = True
            self._set_result("")
        except Exception as error:
            self._set_result(str(error))
        self._update_controls()

    def stop_music(self):
        self._pending_play = None
        self._timeout.stop()
        if self.test_running:
            self._process.kill()
        self.player.stop()
        self._set_result("")
        self.details.hide()
        self._update_controls()

    def poll(self):
        game_mic = self._vrchat_microphone.microphone
        selected = self.settings.mic_device
        mismatch = bool(game_mic and selected and game_mic.casefold() != selected.casefold())
        self.route_warning.setText(tr("VRChat uses {microphone}. Select the same microphone in the translator to send music there.").format(microphone=game_mic) if mismatch else "")
        self.route_warning.setVisible(mismatch)
        microphone_changed = self.player.busy and self.player.microphone != self.settings.mic_device
        if microphone_changed:
            self.stop_music()
            self._set_result(tr("Microphone changed. Start music again to use it."))
            self._attachment = None
        active, busy = self.player.active, self.player.busy
        peak = self.player.source_peak if active else 0.0
        db = max(-60.0, min(0.0, 20 * math.log10(max(peak, 1e-6))))
        self.source_meter.setValue(round(db + 60))
        level_text = f"{db:.0f} dBFS" if peak > .001 else tr("Silent")
        self.source_meter.setToolTip(level_text)
        self.source_meter.setAccessibleDescription(level_text)
        if active != self._was_active:
            self.state_changed.emit(active)
            self._was_active = active
        self.peak_changed.emit(peak)
        if self._was_busy and not busy and not microphone_changed:
            self._set_result(self.player.error)
        self._was_busy = busy
        self._update_controls()

    def run_test(self):
        if self.test_running or self.player.busy or self.setup_running:
            return
        self._test_command = prototype_test_command()
        if not self._test_command:
            self._launch_music()
            return
        self._timed_out = False
        self.details.clear()
        program, arguments, directory = self._test_command
        self._process.setWorkingDirectory(directory)
        self._timeout.start()
        self._process.start(program, arguments)
        self._update_controls()

    def _read_output(self):
        output = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if output:
            self.details.insertPlainText(output)
            self.details.verticalScrollBar().setValue(self.details.verticalScrollBar().maximum())

    def _test_finished(self, code, status):
        self._timeout.stop()
        self._read_output()
        if self._pending_play is None:
            self._update_controls()
            return
        if self._timed_out:
            self._set_result(tr("The internal test timed out. Your microphone settings were not changed."))
        elif code == 0 and status == QProcess.NormalExit:
            self.details.clear()
            self.details.hide()
            self._launch_music()
            return
        else:
            self._set_result(tr("Internal test failed. See the details below."))
        self._pending_play = None
        self.details.show()
        self._update_controls()

    def _test_error(self, error):
        if error == QProcess.FailedToStart:
            self._timeout.stop()
            self._pending_play = None
            self._set_result(tr("Could not start the internal test. See the details below."))
            self.details.appendPlainText(self._process.errorString())
            self.details.show()
            self._update_controls()

    def _test_timeout(self):
        self._timed_out = True
        self._process.kill()

    def reject(self):
        if self.setup_running:
            return
        self.hide()

    def _stop_test(self):
        self._pending_play = None
        self.player.close()
        self.state_changed.emit(False)
        self._timeout.stop()
        if self.test_running:
            self._process.kill()
            self._process.waitForFinished(1000)

    def shutdown(self):
        """Stops playback and tests. Called when the entire app closes."""
        self._shutting_down = True
        self._poll_timer.stop()
        self._route_timer.stop()
        self._stop_test()
        self.close()

    def closeEvent(self, event):
        if getattr(self, "_shutting_down", False):
            event.accept()
            return
        if self.setup_running:
            event.ignore()
            return
        self.hide()
        event.ignore()
