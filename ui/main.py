"""Start the window:  python -m ui.main   (add --demo for example lines instead of VRChat)."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from . import __version__, config, theme

ICON_FILE = Path(__file__).resolve().parent.parent / "assets" / "icon.png"
APP_ID = "SentoMinh.VRChatTranslator"   # Windows groups the taskbar button (and its icon) by this


def program_icon() -> QIcon:
    return QIcon(str(ICON_FILE))


def _own_taskbar_button() -> None:
    """Started from source, the program is python.exe to Windows, and the taskbar would show
    Python's icon. Its own id makes Windows use the window's icon instead."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except (AttributeError, OSError):
            pass
from .backend import Backend
from .demo_backend import DemoBackend
from .live_backend import LiveBackend
from .main_window import MainWindow


def make_on_switch(backend):
    def on_switch(name: str):
        if ":" in name:
            svc, model = name.split(":", 1)
            if hasattr(backend, "current_translating_service"):
                backend.current_translating_service = svc
            if getattr(backend, "current_translating_model", "") != model:
                backend.current_translating_model = model
                backend.setting_switched.emit("translating_model", model)
            if hasattr(backend, "settings") and getattr(backend.settings, "translating", "") != svc:
                backend.setting_switched.emit("translating", svc)
        else:
            if getattr(backend, "current_translating_model", "") != name:
                backend.current_translating_model = name
                backend.setting_switched.emit("translating_model", name)
    return on_switch


def speech_translator(pick=lambda: "", on_switch=None):
    """The explicitly configured models of the service that `pick()` names, also used for
    typed text. None = no engine: typed text is then sent untranslated."""
    try:
        from engine.translators import ServiceChain
        return ServiceChain(pick, on_switch=on_switch)
    except Exception:
        return None


def attach_speech(backend: LiveBackend) -> None:
    """Connect the speech engine (the engine package: sound → text → translation) if it is there.
    A missing or broken engine must not stop the window: the status tooltip says why instead."""
    try:
        from engine import attach
    except ImportError as error:
        backend.speech_problem = f"the speech engine is not installed ({error})"
        return
    try:
        attach(backend)
        backend.speech_ready = True
    except Exception as error:
        backend.speech_problem = str(error) or type(error).__name__


def look_for_update(backend) -> None:
    """Download application updates in the background; show readiness in the status tooltip."""
    from .updater import Updater, program_file
    program = program_file()
    if program is None:
        return                           # from source: run_ui.bat updates through git

    def ready(version: str) -> None:     # called from the download thread; the status poll shows it
        backend.update_note = f"Update downloaded, it starts the next time you open the program: {version}"
    Updater(program, __version__, on_ready=ready).start()


def run(backend: Backend | None = None) -> int:
    _own_taskbar_button()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("VRChat Translator")
    app.setWindowIcon(program_icon())        # title bars, taskbar, the settings window
    app.setStyleSheet(theme.style_sheet())
    if backend is None:
        if "--demo" in sys.argv:
            backend = DemoBackend()
        else:
            # the window hands its settings to the backend; the chain asks them which service
            backend = LiveBackend()
            backend._translator = speech_translator(
                lambda: backend.settings.translating,
                on_switch=make_on_switch(backend))
            attach_speech(backend)
    if isinstance(backend, LiveBackend):
        from .service_health import ServiceHealth
        backend.service_health = ServiceHealth(backend)
        app.aboutToQuit.connect(backend.service_health.stop)
    window = MainWindow(backend, config.load())
    from vr.main import attach_wrist
    wrist = attach_wrist(window)
    app.aboutToQuit.connect(wrist.stop)
    window.show()
    QTimer.singleShot(0, window.show_update_notice)
    if isinstance(backend, LiveBackend):
        QTimer.singleShot(0, backend.service_health.start)
    backend.start()
    wrist.start()
    look_for_update(backend)
    code = app.exec()
    wrist.stop()
    backend.stop()
    return code


if __name__ == "__main__":
    sys.exit(run())
