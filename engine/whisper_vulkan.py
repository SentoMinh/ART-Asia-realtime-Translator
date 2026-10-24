"""Persistent whisper.cpp Vulkan context, loaded only when explicitly selected."""
from __future__ import annotations

import ctypes
import logging
from pathlib import Path
import sys
import threading
import zlib

import numpy as np

from . import local_model
from .stt import CHINESE, RATE, Heard, SttError, tidy

MODEL = "whisper-turbo-vulkan"
log = logging.getLogger(__name__)


def runtime_file() -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return root / "assets" / "whisper-vulkan" / "art_whisper_vulkan.dll"


def library():
    # An absolute path and Windows' safe DLL search keep CWD out of dependency lookup.
    dll = ctypes.CDLL(str(runtime_file()), winmode=0x1100)
    signatures = {
        "abi": (ctypes.c_int, []),
        "error": (ctypes.c_char_p, []),
        "open": (ctypes.c_void_p, [ctypes.c_wchar_p]),
        "free": (None, [ctypes.c_void_p]),
        "device": (ctypes.c_char_p, [ctypes.c_void_p]),
        "run": (ctypes.c_int, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float), ctypes.c_int, ctypes.c_char_p]),
        "language": (ctypes.c_char_p, [ctypes.c_void_p]),
        "segments": (ctypes.c_int, [ctypes.c_void_p]),
        "text": (ctypes.c_char_p, [ctypes.c_void_p, ctypes.c_int]),
        "no_speech": (ctypes.c_float, [ctypes.c_void_p, ctypes.c_int]),
        "logprob": (ctypes.c_float, [ctypes.c_void_p, ctypes.c_int]),
    }
    for name, (result, args) in signatures.items():
        function = getattr(dll, "art_whisper_" + name)
        function.restype, function.argtypes = result, args
    if dll.art_whisper_abi() != 1:
        raise SttError("Whisper Vulkan runtime version does not match this app")
    return dll


class VulkanWhisper:
    name = "local"

    def __init__(self):
        self._dll = None
        self._context = None
        self._lock = threading.RLock()

    def load(self):
        with self._lock:
            if self._context:
                return
            problem = local_model.missing(MODEL)
            if problem:
                raise SttError(problem)
            try:
                self._dll = library()
                self._context = self._dll.art_whisper_open(str(local_model.model_folder(MODEL) / "model.bin"))
                if not self._context:
                    raise SttError(self._error())
                log.info("Whisper Vulkan GPU: %s", self._dll.art_whisper_device(self._context).decode("utf-8", "replace"))
                self._run(np.zeros(RATE, dtype=np.float32), "en")
            except SttError:
                self.close()
                raise
            except (OSError, AttributeError) as error:
                self.close()
                raise SttError(f"Whisper Vulkan could not load. Check the Vulkan graphics driver: {error}") from error

    def _error(self):
        return (self._dll.art_whisper_error() or b"Whisper Vulkan failed").decode("utf-8", "replace")

    def close(self):
        with self._lock:
            if self._context:
                self._dll.art_whisper_free(self._context)
                self._context = None

    def transcribe(self, samples, lang, prefer=()) -> Heard:
        if lang is not None and lang not in ("en", "zh", "yue", "vi", "ja", "ko"):
            raise SttError("Whisper Vulkan language is not supported by this app")
        audio = np.ascontiguousarray(samples, dtype=np.float32)
        if audio.ndim != 1 or not np.isfinite(audio).all():
            raise SttError("Whisper Vulkan needs finite mono speech samples")
        if not audio.size:
            return Heard()
        with self._lock:
            self.load()
            # Preserve the existing Mandarin/Cantonese distinction before forcing Chinese.
            text, code = self._run(audio, None if lang == "zh" else lang)
            if lang == "zh" and code not in CHINESE:
                text, code = self._run(audio, "zh")
            return tidy(text, code)

    def _run(self, audio, lang):
        result = self._dll.art_whisper_run(self._context,
                    audio.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), len(audio),
                    lang.encode("ascii") if lang else None)
        if result:
            raise SttError(self._error())
        code = (self._dll.art_whisper_language(self._context) or b"").decode("ascii")
        kept = []
        for i in range(self._dll.art_whisper_segments(self._context)):
            raw = self._dll.art_whisper_text(self._context, i) or b""
            no_speech = self._dll.art_whisper_no_speech(self._context, i)
            confidence = self._dll.art_whisper_logprob(self._context, i)
            if no_speech > 0.6 and confidence < -1.0:
                continue
            if len(raw) / len(zlib.compress(raw)) > 2.6:
                continue
            kept.append(raw.decode("utf-8"))
        return "".join(kept).strip(), code
