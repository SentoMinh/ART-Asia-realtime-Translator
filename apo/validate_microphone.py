"""Opt-in live test: send a quiet one-second tone through the installed mixer.

Apps using the microphone may hear it. Captured audio stays in memory; the report
contains only tone measurements. No speech recording is saved.
"""
from pathlib import Path
import json
import sys
import tempfile
import subprocess
import time
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import sounddevice as sd
from vrc.apo_player import ApoPlayer, attachment_for
from vrc.apo_setup import load_state
from vrc import apo_music


def measure(samples, rate):
    if len(samples) < rate / 20:
        raise RuntimeError("Not enough microphone samples for measurement.")
    values = np.asarray(samples, dtype=np.float64)
    window = np.hanning(len(values))
    phase = np.exp(-2j * np.pi * 997 * np.arange(len(values)) / rate)
    return float(2 * abs(np.sum(values * window * phase)) / window.sum())


def tone_player():
    position = 0
    def output(data, frames, *_):
        nonlocal position
        signal = .02 * np.sin(2 * np.pi * 997 * (np.arange(frames) + position) / 48000)
        data[:] = signal[:, None]
        position += frames
    with sd.OutputStream(samplerate=48000, channels=2, dtype="float32", callback=output):
        print("ready", flush=True)
        time.sleep(10)


def main(app_capture=False):
    state = load_state()
    if not state or not attachment_for(state.get("microphone")):
        raise RuntimeError("A validated microphone attachment is required.")
    apis = sd.query_hostapis()
    matches = [(i, d) for i, d in enumerate(sd.query_devices()) if d["name"] == state["microphone"]
               and d["max_input_channels"] > 0 and "WASAPI" in apis[d["hostapi"]]["name"]]
    if len(matches) != 1:
        raise RuntimeError("Microphone could not be matched uniquely.")
    index, device = matches[0]
    rate = int(device["default_samplerate"])
    blocks = []
    player = ApoPlayer()
    child = None
    source_blocks = []
    capture_factory = apo_music.audio.ProcessAudioCapture
    if app_capture:
        def observed_capture(pid, on_data):
            def received(data, frames):
                source_blocks.append(np.frombuffer(data, dtype=np.float32).reshape(-1, 2)[:, 0].copy())
                on_data(data, frames)
            return capture_factory(pid, on_data=received)
        apo_music.audio.ProcessAudioCapture = observed_capture
    try:
        with tempfile.TemporaryDirectory(prefix="vrct-live-test-") as directory:
            path = Path(directory) / "quiet-test.wav"
            signal = .02 * np.sin(2 * np.pi * 997 * np.arange(48000) / 48000)
            with wave.open(str(path), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(48000)
                output.writeframes((signal * 32767).astype("<i2").tobytes())
            with sd.InputStream(device=index, samplerate=rate, channels=1, dtype="float32",
                                callback=lambda data, *args: blocks.append(data[:, 0].copy())):
                if app_capture:
                    child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--tone-player"],
                                             stdout=subprocess.PIPE, text=True, creationflags=0x08000000)
                    if child.stdout.readline().strip() != "ready":
                        raise RuntimeError("The isolated test sound app could not start.")
                time.sleep(.4)
                before = np.concatenate(blocks) if blocks else np.array([])
                begin = len(before)
                player.start("app" if app_capture else "wav", child.pid if child else path, state["microphone"])
                if app_capture:
                    # Process capture starts asynchronously. Exclude device/COM
                    # startup from the playback measurement, but keep a timeout.
                    deadline = time.monotonic() + 5
                    while player.source_peak < .001 and player.busy and time.monotonic() < deadline:
                        time.sleep(.02)
                    if not player.active or player.source_peak < .001:
                        raise RuntimeError(player.error or "App capture did not start in time.")
                    begin = sum(len(block) for block in blocks)
                    time.sleep(1.5)
                    player.stop()
                deadline = time.monotonic() + 5
                while player.busy and time.monotonic() < deadline:
                    time.sleep(.02)
                if player.busy or player.error:
                    raise RuntimeError(player.error or "Playback did not stop in time.")
                end = sum(len(block) for block in blocks)
                time.sleep(.4)
            samples = np.concatenate(blocks)
            middle = samples[begin + rate // 4:end - rate // 5]
            baseline = measure(before, rate)
            during = measure(middle, rate)
            after = measure(samples[end + rate // 10:], rate)
            source_amplitude = measure(np.concatenate(source_blocks), 48000) if source_blocks else .02
            # Windows app/session volume affects captured source level. Compare
            # against measured source amplitude instead of assuming unity gain.
            passed = during > max(baseline, after, .0001) * 4 and during > source_amplitude * .2
            report = {"microphone": state["microphone"], "tone_hz": 997,
                      "source": "selected app" if app_capture else "WAV file",
                      "source_amplitude": source_amplitude,
                      "baseline_amplitude": baseline, "playing_amplitude": during,
                      "after_stop_amplitude": after, "passed": passed,
                      "speech_recording_saved": False}
            print(json.dumps(report, indent=2))
            return 0 if passed else 1
    finally:
        player.close()
        apo_music.audio.ProcessAudioCapture = capture_factory
        if child:
            child.terminate()
            child.wait(timeout=5)


if __name__ == "__main__":
    if "--tone-player" in sys.argv:
        tone_player()
    else:
        raise SystemExit(main(app_capture="--app" in sys.argv))
