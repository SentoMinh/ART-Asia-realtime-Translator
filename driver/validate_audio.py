"""Read-only endpoint check by default; --run explicitly streams a test signal.

Run only in an isolated Windows test VM with the driver installed and all voice
chat/translator apps closed. No physical microphone or default audio device is used.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import time

import numpy as np

RATE = 48000
MIX = "VRChat Translator Mix"
MUSIC = "VRChat Translator Music"
MIC = "VRChat Translator Microphone"


def select_device(devices, apis, name, direction):
    matches = [index for index, device in enumerate(devices)
               if name in device["name"] and device[f"max_{direction}_channels"] >= 2
               and "WASAPI" in apis[device["hostapi"]]["name"]]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one stereo WASAPI {name}; found {len(matches)}. No fallback used.")
    return matches[0]


def test_signal():
    # Independent channels detect swaps, mono collapse, clipping and sample loss.
    rng = np.random.default_rng(1234)
    signal = rng.integers(-2000, 2001, size=(RATE, 2), dtype=np.int16)
    return signal.astype(np.float32) / 32768


def analyze(reference, recording):
    if recording.ndim != 2 or recording.shape[1] != 2 or len(recording) < len(reference):
        raise ValueError("Capture is too short or is not stereo")
    if not np.isfinite(recording).all():
        raise ValueError("Capture contains non-finite samples")
    # FFT correlation finds the capture offset without a quadratic-time search.
    length = len(recording) + len(reference) - 1
    size = 1 << (length - 1).bit_length()
    correlation = np.fft.irfft(np.fft.rfft(recording[:, 0], size) *
                               np.fft.rfft(reference[::-1, 0], size), size)
    candidates = correlation[len(reference) - 1:len(recording)]
    offset = int(np.argmax(candidates))
    aligned = recording[offset:offset + len(reference)]
    error = float(np.sqrt(np.mean((aligned - reference).astype(np.float64) ** 2)))
    level = float(np.sqrt(np.mean(reference.astype(np.float64) ** 2)))
    tail = recording[offset + len(reference) + RATE // 5:]
    tail_peak = float(np.max(np.abs(tail))) if len(tail) else None
    relative_error = error / max(level, 1e-9)
    return {"offset_frames": offset, "relative_rms_error": relative_error,
            "tail_peak": tail_peak,
            "passed": relative_error < 0.02 and tail_peak is not None and tail_peak < 0.0001}


def capture(sd, output, microphone, signal):
    chunks, flags = [], []

    def received(data, frames, timing, status):
        if status:
            flags.append(str(status))
        chunks.append(data.copy())

    with sd.InputStream(device=microphone, samplerate=RATE, channels=2,
                        dtype="float32", blocksize=480, callback=received):
        time.sleep(0.2)
        with sd.OutputStream(device=output, samplerate=RATE, channels=2,
                             dtype="float32", blocksize=480) as render:
            for start in range(0, len(signal), 480):
                if render.write(signal[start:start + 480]):
                    flags.append("render underflow")
        time.sleep(0.8)
    if not chunks:
        raise RuntimeError("No microphone samples received")
    return np.concatenate(chunks), flags


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Stream test audio; close all voice chat apps first")
    parser.add_argument("--report", type=Path, default=Path("audio-validation.json"))
    args = parser.parse_args()
    report = {"platform": platform.platform(), "streaming_requested": args.run}
    try:
        import sounddevice as sd
        devices, apis = sd.query_devices(), sd.query_hostapis()
        chosen = {name: select_device(devices, apis, name, direction) for name, direction in
                  ((MIX, "output"), (MUSIC, "output"), (MIC, "input"))}
        report["devices"] = {name: devices[index]["name"] for name, index in chosen.items()}
        if args.run:
            signal = test_signal()
            results = []
            for cycle in range(2):
                recorded, flags = capture(sd, chosen[MIX], chosen[MIC], signal)
                result = analyze(signal, recorded)
                result.update(cycle=cycle + 1, callback_flags=flags)
                result["passed"] = result["passed"] and not flags
                results.append(result)
            recorded, flags = capture(sd, chosen[MUSIC], chosen[MIC], signal)
            peak = float(np.max(np.abs(recorded)))
            report.update(mix_cycles=results, music_isolation_peak=peak, isolation_flags=flags)
            report["passed"] = all(item["passed"] for item in results) and peak < 0.0001 and not flags
        else:
            report["endpoints_present"] = True
            report["note"] = "No streaming performed; endpoint presence is not a functional audio test."
    except Exception as error:
        report.update(passed=False, error=str(error))
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if report.get("passed") is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
