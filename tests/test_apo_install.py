from contextlib import nullcontext
import json
from types import SimpleNamespace

import pytest

from vrc import apo_install as installer


@pytest.fixture(autouse=True)
def isolated_attachment(monkeypatch):
    monkeypatch.setattr(installer.apo_setup, "load_state", lambda: None)


def test_installed_mixer_does_not_request_admin_or_restart_audio(monkeypatch):
    monkeypatch.setattr(installer, "installed", lambda _: True)
    monkeypatch.setattr(installer.subprocess, "run", lambda *a, **kw: pytest.fail("Must not elevate"))
    assert installer.install("HyperX") == {"ok": True, "already_installed": True}


def test_other_microphone_reports_existing_attachment_before_setup(monkeypatch):
    monkeypatch.setattr(installer.apo_setup, "load_state", lambda: {
        "phase": "validated", "microphone": "Virtual Desktop Audio"})
    monkeypatch.setattr(installer, "installed", lambda name: name == "Virtual Desktop Audio")
    monkeypatch.setattr(installer, "native_build", lambda: pytest.fail("Must not prepare a second installation"))
    monkeypatch.setattr(installer.subprocess, "run", lambda *a, **kw: pytest.fail("Must not elevate"))
    with pytest.raises(RuntimeError, match="already installed on Virtual Desktop Audio"):
        installer.install("HyperX")


def test_registered_microphone_requires_validated_unchanged_installation(monkeypatch):
    state = {"phase": "removed", "microphone": "Headset"}
    monkeypatch.setattr(installer.apo_setup, "load_state", lambda: state)
    monkeypatch.setattr(installer, "installed", lambda _: pytest.fail("Removed attachment must not be used"))
    assert installer.registered_microphone() == ""
    state["phase"] = "validated"
    def changed(_):
        raise RuntimeError("configuration changed")
    monkeypatch.setattr(installer, "installed", changed)
    with pytest.raises(RuntimeError, match="configuration changed"):
        installer.registered_microphone()


def test_frozen_setup_uses_bundled_executable(monkeypatch):
    monkeypatch.setattr(installer.sys, "frozen", True, raising=False)
    monkeypatch.setattr(installer.sys, "executable", "C:/App/Translator.exe")
    assert installer.setup_command("HyperX") == (
        "C:/App/Translator.exe", ["--mixer-setup", "--microphone", "HyperX"])


def test_setup_writes_result_for_windowed_executable(monkeypatch, tmp_path):
    report = tmp_path / "result.json"
    monkeypatch.setattr(installer.sys, "argv", ["setup", "--microphone", "HyperX", "--report", str(report)])
    monkeypatch.setattr(installer, "installed", lambda _: True)
    assert installer.main() == 0
    assert json.loads(report.read_text()) == {"ok": True, "already_installed": True}


@pytest.fixture
def ready(monkeypatch, tmp_path):
    checks = iter([False, True])
    monkeypatch.setattr(installer, "installed", lambda _: next(checks))
    monkeypatch.setattr(installer, "native_build", lambda: tmp_path)
    monkeypatch.setattr(installer, "endpoint_for", lambda _: "endpoint")
    monkeypatch.setattr(installer.apo_setup, "current_sid", lambda: "user-sid")
    monkeypatch.setattr(installer.apo_setup, "make_plan", lambda *a: {})
    monkeypatch.setattr(installer.tempfile, "TemporaryDirectory", lambda **kw: nullcontext(str(tmp_path)))
    return tmp_path


def test_uac_launch_uses_local_files_and_keeps_device_name_out_of_shell_code(monkeypatch, ready):
    mic = "Microphone (A & B $device)"
    def run(command, **kwargs):
        assert "-Verb RunAs" in command[-1]
        assert mic not in command[-1]
        assert mic in kwargs["env"]["VRCT_SETUP_ARGS"]
        assert "--elevated" in kwargs["env"]["VRCT_SETUP_ARGS"]
        (ready / "result.json").write_text(json.dumps({"ok": True}))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(installer.subprocess, "run", run)
    assert installer.install(mic) == {"ok": True, "already_installed": False}


def test_cancelled_admin_prompt_does_not_report_success(monkeypatch, ready):
    monkeypatch.setattr(installer.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=1, stdout="Cancelled"))
    with pytest.raises(RuntimeError, match="cancelled"):
        installer.install("HyperX")


def test_failed_elevated_install_reports_actual_error(monkeypatch, ready):
    def run(*a, **kw):
        (ready / "result.json").write_text(json.dumps({"ok": False, "error": "Existing effects preserved"}))
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(installer.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="Existing effects preserved"):
        installer.install("HyperX")
