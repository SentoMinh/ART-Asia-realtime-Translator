"""The speech engine: live sound -> sentences -> text -> translation.

The window calls attach(backend) once, before backend.start(). It returns at once: the
speech model loads on the engine's own thread, and backend.speech_status says how far it is.
"""
from __future__ import annotations

import importlib.util
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

NEEDED = {"onnxruntime": "onnxruntime", "soxr": "soxr", "httpx": "httpx"}

# Native runtimes read these at import/initialization, before any model is loaded.
from .runtime import configure_native_threads
configure_native_threads()


def log_file() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "VRChat-Translator" / "engine.log"


def _log_to_file() -> None:
    logger = logging.getLogger("engine")
    if logger.handlers:
        return
    try:
        log_file().parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(log_file(), maxBytes=1_000_000, backupCount=1, encoding="utf-8")
    except OSError:
        return
    handler.setFormatter(logging.Formatter("%(asctime)s %(threadName)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def attach(backend):
    """Connect the speech engine to the window's backend. Raises RuntimeError with a
    plain-words reason if it can't work in this Python environment."""
    missing = [package for module, package in NEEDED.items() if importlib.util.find_spec(module) is None]
    if missing:
        raise RuntimeError(f"these packages are not installed: {', '.join(missing)}")
    _log_to_file()
    from .speech import SpeechEngine
    engine = SpeechEngine(backend)
    engine.start()
    backend.speech_engine = engine      # kept alive with the backend
    return engine
