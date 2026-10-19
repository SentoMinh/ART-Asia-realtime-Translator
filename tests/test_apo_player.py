from contextlib import nullcontext
import time

import pytest

from vrc import apo_player


def wait_stopped(player):
    until = time.monotonic() + 2
    while player.busy and time.monotonic() < until:
        time.sleep(.01)
    assert not player.busy


def test_playback_uses_installed_mixer_and_stop_closes_worker(monkeypatch):
    monkeypatch.setattr(apo_player, "attachment_for", lambda _: {"directory": "C:/fixture", "token": "token"})
    captures = []
    monkeypatch.setattr(apo_player.apo_setup, "open_capture", lambda mic: captures.append(mic) or nullcontext())
    monkeypatch.setattr(apo_player, "probe", lambda *a: 2)
    received = []
    def play(library, token, source, stop, *, gain, on_level):
        received.append((token, source, gain()))
        on_level(.2)
        stop.wait(2)
    monkeypatch.setattr(apo_player.apo_music, "play_file", play)
    player = apo_player.ApoPlayer()
    player.gain = .3
    player.start("wav", "music.wav", "HyperX")
    until = time.monotonic() + 2
    while not received and time.monotonic() < until:
        time.sleep(.01)
    assert player.active
    assert player.source_peak == .2
    assert captures == ["HyperX"]
    assert received == [("token", "music.wav", .3)]
    player.close()
    assert not player.busy and not player.active and not player.error
    assert player.source_peak == 0


def test_source_meter_expires_after_capture_stalls(monkeypatch):
    now = [10.0]
    monkeypatch.setattr(apo_player.time, "monotonic", lambda: now[0])
    player = apo_player.ApoPlayer()
    player.active = True
    player._source_level(.4)
    now[0] += .1
    player._source_level(0)
    assert player.source_peak == .4
    now[0] += .2
    player._source_level(0)
    assert player.source_peak == 0
    player._source_level(.2)
    now[0] += .6
    assert player.source_peak == 0


def test_missing_attachment_never_opens_capture(monkeypatch):
    monkeypatch.setattr(apo_player, "attachment_for", lambda _: None)
    monkeypatch.setattr(apo_player.apo_setup, "open_capture", lambda _: pytest.fail("No microphone should be opened"))
    with pytest.raises(RuntimeError, match="not installed"):
        apo_player.ApoPlayer().start("wav", "music.wav", "Other mic")


def test_sender_failure_is_reported_and_capture_is_closed(monkeypatch):
    monkeypatch.setattr(apo_player, "attachment_for", lambda _: {"directory": "C:/fixture", "token": "token"})
    closed = []
    class Capture:
        def __enter__(self): return self
        def __exit__(self, *args): closed.append(True)
    monkeypatch.setattr(apo_player.apo_setup, "open_capture", lambda _: Capture())
    monkeypatch.setattr(apo_player, "probe", lambda *args: 2)
    def fail(*args, **kwargs): raise RuntimeError("source disappeared")
    monkeypatch.setattr(apo_player.apo_music, "play_process", fail)
    player = apo_player.ApoPlayer()
    player.start("app", 123, "HyperX")
    wait_stopped(player)
    assert player.error == "source disappeared"
    assert closed == [True]
    assert not player.active
