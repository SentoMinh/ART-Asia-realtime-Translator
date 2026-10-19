"""Run Python-to-native APO playback in a temporary standalone host, not audiodg."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
import wave

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build_directory", type=Path)
    args = parser.parse_args()
    build = args.build_directory.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="vrct-apo-test-") as temporary:
        fixture = Path(temporary) / "music.wav"
        with wave.open(str(fixture), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(44100)
            output.writeframes(np.full(22050, 8192, dtype="<i2").tobytes())
        result = subprocess.run([
            str(build / "ApoTests.exe"), str(build / "VrctMicApo-Test.dll"),
            str(build / "VrctApoProducer.dll"), sys.executable, str(fixture),
        ], cwd=Path(__file__).resolve().parents[1], check=False, timeout=30)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
