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


def latest_microphone(path, started, start=0):
    """(microphone of the last complete event after byte `start`, or None when there is none;
    the byte where the complete lines end). At most the last MAX_LOG_BYTES are read."""
    with path.open("rb") as source:
        end = source.seek(0, 2)
        start = source.seek(max(start, end - MAX_LOG_BYTES))
        data = source.read(end - start)
    data = data[:data.rfind(b"\n") + 1]
    text = data.decode("utf-8", errors="replace").replace("\r\n", "\n")
    event = None
    for event in _EVENT.finditer(text):
        pass
    if event is None:
        return None, start + len(data)
    timestamp = datetime.strptime(event[1], "%Y.%m.%d %H:%M:%S").timestamp()
    found = event[3].strip() if event[2] == "Start" and timestamp >= started - 1 else ""
    return found, start + len(data)


def logged_microphone(path, started):
    """Unknown/stopped is empty. Ignore partial lines and earlier game sessions."""
    return latest_microphone(path, started)[0] or ""


class MicrophoneStatus:
    """One bounded background read at a time; the UI only consumes a string."""
    def __init__(self):
        self.microphone = ""
        self._thread = None
        self._session = None
        self._read_to = 0         # the log grows all the time: only lines after this byte are new

    def refresh(self):
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._read, daemon=True)
            self._thread.start()

    def _read(self):
        try:
            pids = process_ids()
            if len(pids) != 1:
                self.microphone = ""
                self._session = None
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
            session = (pids[0], started, path)
            fresh = session != self._session or path.stat().st_size < self._read_to
            found, self._read_to = latest_microphone(path, started, 0 if fresh else self._read_to)
            if found is not None or fresh:
                self.microphone = found or ""
            self._session = session
        except (OSError, ValueError, AttributeError):
            self.microphone = ""
            self._session = None
