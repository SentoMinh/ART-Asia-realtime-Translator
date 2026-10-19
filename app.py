"""Program start (this is what VRChat-Translator.exe runs).

    VRChat-Translator.exe              the translator window
    VRChat-Translator.exe --demo       example lines, no connection to VRChat
    VRChat-Translator.exe --selfcheck  loads every part once, writes selfcheck.txt, and exits
                 (with --get-local-model it first downloads the Local Model's 2 GB if missing)
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def report_file() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "VRChat-Translator" / "selfcheck.txt"


def selfcheck() -> int:
    """Proves that the packaged program contains everything it needs, without opening the
    window or touching VRChat."""
    lines, failed = [], 0

    def check(name, action):
        nonlocal failed
        try:
            lines.append(f"ok    {name}: {action()}")
        except Exception:
            failed += 1
            lines.append(f"FAIL  {name}: {traceback.format_exc().strip().splitlines()[-1]}")

    def window():
        from PySide6.QtWidgets import QApplication
        from ui import theme
        from ui.config import Settings
        from ui.demo_backend import DemoBackend
        from ui.main_window import MainWindow
        app = QApplication.instance() or QApplication(sys.argv[:1])
        app.setStyleSheet(theme.style_sheet())
        MainWindow(DemoBackend(), Settings(), save=lambda s: None)
        return "built"

    def version():
        import ui
        return ui.__version__

    def icon():
        from ui.main import ICON_FILE, program_icon
        sizes = program_icon().availableSizes()
        if not ICON_FILE.exists() or not sizes:
            raise RuntimeError(f"the icon is missing: {ICON_FILE}")
        return f"{sizes[0].width()} px"

    def microphones():
        from vrc import audio
        if audio.sounddevice is None:
            raise RuntimeError("sounddevice is missing")
        return f"{len(audio.input_devices())} found"

    def game_capture():
        from vrc import audio
        if audio.ProcessAudioCapture is None:
            raise RuntimeError("proc-tap is missing")
        return "proc-tap present"

    def music_mixer():
        import ctypes
        from vrc.apo_install import native_build, setup_command
        from ui.music_dialog import MusicDialog
        from ui.config import Settings
        build = native_build()
        if build is None:
            raise RuntimeError("Microphone mixer files are missing")
        dll = ctypes.CDLL(str(build / "VrctMicApo.dll"))
        dll.VrctApoBuildKind.restype = ctypes.c_int
        if dll.VrctApoBuildKind() != 1:
            raise RuntimeError("Wrong microphone mixer build")
        dialog = MusicDialog(Settings())
        dialog.close()
        setup_command("Microphone")
        return "production mixer and setup launcher included; no installation performed"

    def vrchat():
        from vrc.chatbox import encode_message, find_vrchat
        encode_message("/chatbox/input", "test", True, False)
        return find_vrchat()

    def detector():
        import numpy as np
        from engine.vad import FRAME, SileroVad
        return f"probability {float(SileroVad().probabilities(np.zeros(FRAME, dtype='float32'))[0]):.3f}"

    def resampler():
        import numpy as np
        import soxr
        return len(soxr.resample(np.zeros(4800, dtype="float32"), 48000, 16000))

    def hearing():
        from engine import services
        from engine.stt import CloudHearing, tidy
        from ui import config
        tidy("你好", "zh")
        chosen = config.load().hearing
        if chosen == "local":
            return "Local Model"
        return f"{services.title(chosen)}: " + (CloudHearing(chosen).missing() or "ready")

    def local_model():
        import time
        from engine import local_model as local
        from engine import stt
        if not local.installed():
            return "not in this copy"
        stt.whisper_class()                    # the model's own code is all there
        if local.missing() and "--get-local-model" in sys.argv:
            local.download()
        problem = local.missing()
        if problem:
            return problem
        started = time.perf_counter()
        stt.LocalWhisper().load()
        return f"loaded on the graphics card in {time.perf_counter() - started:.1f} s"

    def translators():
        from engine import services
        from engine.translators import ServiceChain
        from ui import config
        chosen = config.load().translating
        return f"{services.title(chosen)}: " + ", ".join(ServiceChain(lambda: chosen).names())

    def https():
        import httpx
        with httpx.Client(timeout=10) as client:
            return client.get("https://api.github.com").status_code    # where updates come from

    for name, action in (("version", version), ("window", window), ("icon", icon),
                         ("microphones", microphones),
                         ("VRChat sound capture", game_capture), ("VRChat detection", vrchat),
                         ("music mixer", music_mixer),
                         ("voice detector", detector), ("resampler", resampler),
                         ("hearing engine", hearing), ("Local Model", local_model),
                         ("translators", translators),
                         ("secure connection", https)):
        check(name, action)
    lines.append("RESULT: " + ("all parts work" if not failed else f"{failed} part(s) failed"))
    try:
        report_file().parent.mkdir(parents=True, exist_ok=True)
        report_file().write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        pass
    return 1 if failed else 0


def main() -> int:
    if "--mixer-setup" in sys.argv:
        sys.argv.remove("--mixer-setup")
        from vrc.apo_install import main as mixer_setup
        return mixer_setup()
    from ui.updater import apply_pending, program_file
    program = program_file()
    if program is not None and apply_pending(program):
        return 0                             # a downloaded update is starting instead
    if "--selfcheck" in sys.argv:
        return selfcheck()
    from ui.main import run
    return run()


if __name__ == "__main__":
    sys.exit(main())
