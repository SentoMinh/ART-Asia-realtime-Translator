"""Read VRChat's current-session microphone log without touching its settings."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
import re
import threading

from .chatbox import process_ids

_EVENT = re.compile(
    r"^(\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2}) Debug\s+-\s+"
    r"uSpeak \[[^\]\r\n]*\]\[[^\]\r\n]*\]: (Start|Stop) Microphone: ([^\r\n]*)$",
    re.MULTILINE,
)
MAX_LOG_BYTES = 8 * 1024 * 1024


def process_started(pid):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
            return None
        created = times[0]
        return ((created.dwHighDateTime << 32) | created.dwLowDateTime) / 10_000_000 - 11644473600
    finally:
        kernel.CloseHandle(handle)


def logged_microphone(path, started):
    """Unknown/stopped is empty. Ignore partial lines and earlier game sessions."""
    with path.open("rb") as source:
        source.seek(0, 2)
        source.seek(max(0, source.tell() - MAX_LOG_BYTES))
        data = source.read(MAX_LOG_BYTES)
    data = data[:data.rfind(b"\n") + 1]
    text = data.decode("utf-8", errors="replace").replace("\r\n", "\n")
    for event in reversed(list(_EVENT.finditer(text))):
        timestamp = datetime.strptime(event[1], "%Y.%m.%d %H:%M:%S").timestamp()
        if timestamp < started - 1:
            return ""
        return event[3].strip() if event[2] == "Start" else ""
    return ""


class MicrophoneStatus:
    """One bounded background read at a time; the UI only consumes a string."""
    def __init__(self):
        self.microphone = ""
        self._thread = None
        self._signature = None

    def refresh(self):
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._read, daemon=True)
            self._thread.start()

    def _read(self):
        try:
            pids = process_ids()
            if len(pids) != 1:
                self.microphone = ""
                self._signature = None
                return
            started = process_started(pids[0])
            if started is None:
                self.microphone = ""
                return
            folder = Path.home() / "AppData/LocalLow/VRChat/VRChat"
            paths = sorted(folder.glob("output_log_*.txt"), reverse=True)
            path = next((p for p in paths if started - 1 <= p.stat().st_ctime <= started + 60), None)
            if path is None:
                self.microphone = ""
                return
            stat = path.stat()
            signature = (pids[0], started, path, stat.st_mtime_ns, stat.st_size)
            if signature != self._signature:
                self.microphone = logged_microphone(path, started)
                self._signature = signature
        except (OSError, ValueError, AttributeError):
            self.microphone = ""
            self._signature = None
