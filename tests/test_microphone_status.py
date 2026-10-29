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


def test_growing_log_is_read_from_where_the_last_read_stopped(tmp_path, monkeypatch):
    folder = tmp_path / "AppData/LocalLow/VRChat/VRChat"
    folder.mkdir(parents=True)
    log = folder / "output_log_2026-10-26.txt"
    log.write_bytes(b"")
    started = log.stat().st_ctime
    stamp = datetime.fromtimestamp(started + 5).strftime("%Y.%m.%d %H:%M:%S")
    monkeypatch.setattr(status.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(status, "process_ids", lambda: [7])
    monkeypatch.setattr(status, "process_started", lambda _: started)
    reads, original = [], status.latest_microphone
    monkeypatch.setattr(status, "latest_microphone",
                        lambda path, began, start=0: reads.append(start) or original(path, began, start))
    monitor = status.MicrophoneStatus()

    def append(text):
        with log.open("ab") as handle:
            handle.write(text.encode())
        monitor._read()

    append(event(mic="HyperX", stamp=stamp) + "Chat noise\r\n")
    assert monitor.microphone == "HyperX" and reads == [0]
    append("More chat noise\r\n")
    assert monitor.microphone == "HyperX" and reads[-1] == len(event(mic="HyperX", stamp=stamp)) + 12
    append(event("Stop", stamp=stamp).rstrip())     # still being written
    assert monitor.microphone == "HyperX"
    append("\r\n")
    assert monitor.microphone == ""
    assert monitor._read_to == log.stat().st_size
    log.write_bytes(event(mic="New session mic", stamp=stamp).encode())   # shorter: read again from the start
    monitor._read()
    assert monitor.microphone == "New session mic" and reads[-1] == 0


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
