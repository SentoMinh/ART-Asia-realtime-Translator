from datetime import datetime

import pytest

from vrc import microphone_status as status

STARTED = datetime(2026, 10, 17, 5, 3, 44).timestamp()


def event(action="Start", mic="Microphone (Virtual Desktop Audio)", stamp="2026.10.17 05:20:02"):
    return f"{stamp} Debug      -  uSpeak [650][-123]: {action} Microphone: {mic}\r\n"


@pytest.mark.parametrize("text, expected", [
    (event(), "Microphone (Virtual Desktop Audio)"),
    (event(mic="HyperX") + event(), "Microphone (Virtual Desktop Audio)"),
    (event() + event("Stop"), ""),
    (event(stamp="2026.10.16 05:20:02"), ""),
    ("Chat text: Start Microphone: HyperX\n", ""),
    (event() + event(mic="HyperX").rstrip(), "Microphone (Virtual Desktop Audio)"),
])
def test_read_latest_complete_current_session_event(tmp_path, text, expected):
    path = tmp_path / "output_log.txt"
    path.write_bytes(text.encode())
    assert status.logged_microphone(path, STARTED) == expected


def test_exit_clears_previous_microphone(monkeypatch):
    monitor = status.MicrophoneStatus()
    monitor.microphone = "HyperX"
    monkeypatch.setattr(status, "process_ids", lambda: [])
    monitor._read()
    assert monitor.microphone == ""


def test_multiple_running_games_are_not_guessed(monkeypatch):
    monitor = status.MicrophoneStatus()
    monkeypatch.setattr(status, "process_ids", lambda: [1, 2])
    monkeypatch.setattr(status, "process_started", lambda _: pytest.fail("Ambiguous session"))
    monitor._read()
    assert monitor.microphone == ""
