"""Find the running VRChat and write to its chatbox over OSC (UDP, no extra packages).

VRChat listens on 127.0.0.1:9000 once OSC is enabled (Action Menu → Options → OSC).
UDP gives no answer, so "sent" means: the packet left while VRChat was listening.
"""
from __future__ import annotations

import ctypes
import socket
import struct
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass

HOST = "127.0.0.1"
PORT = 9000
MAX_CHARS = 144        # VRChat cuts chatbox text after this
MIN_GAP_S = 1.5        # faster than this and VRChat mutes the chatbox for ~30 s
QUIET_S = 30.0         # this long without a message: the next one is announced with typing dots
PROCESS_NAME = "vrchat.exe"


@dataclass
class VRChatState:
    running: bool = False
    pid: int = 0
    listening: bool = False   # OSC is enabled: VRChat holds the UDP port

    @property
    def ready(self) -> bool:
        return self.running and self.listening


# ---- finding VRChat ---------------------------------------------------------

class _ProcessEntry(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]


def process_ids(name: str = PROCESS_NAME) -> list[int]:
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)]
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)   # TH32CS_SNAPPROCESS
    if snapshot in (None, wintypes.HANDLE(-1).value):
        return []
    found = []
    entry = _ProcessEntry()
    entry.dwSize = ctypes.sizeof(_ProcessEntry)
    try:
        more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            if entry.szExeFile.lower() == name:
                found.append(entry.th32ProcessID)
            more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return found


def udp_port_owners(port: int = PORT) -> set[int]:
    """Process ids that hold this UDP port."""
    iphlpapi = ctypes.windll.iphlpapi
    size = wintypes.DWORD(0)
    iphlpapi.GetExtendedUdpTable(None, ctypes.byref(size), False, socket.AF_INET, 1, 0)
    for _ in range(3):   # the table can grow between the two calls
        buffer = ctypes.create_string_buffer(size.value)
        result = iphlpapi.GetExtendedUdpTable(buffer, ctypes.byref(size), False, socket.AF_INET, 1, 0)
        if result == 0:
            break
    else:
        return set()
    return parse_udp_table(buffer.raw, port)


def parse_udp_table(raw: bytes, port: int) -> set[int]:
    """MIB_UDPTABLE_OWNER_PID: a count, then (address, port in network order, pid) rows."""
    owners = set()
    count = struct.unpack_from("<I", raw, 0)[0]
    for index in range(count):
        _address, raw_port, pid = struct.unpack_from("<III", raw, 4 + index * 12)
        if socket.ntohs(raw_port & 0xFFFF) == port:
            owners.add(pid)
    return owners


def find_vrchat(port: int = PORT) -> VRChatState:
    pids = process_ids()
    if not pids:
        return VRChatState()
    owners = udp_port_owners(port)
    return VRChatState(running=True, pid=pids[0], listening=any(pid in owners for pid in pids))


# ---- OSC --------------------------------------------------------------------

def _padded(data: bytes) -> bytes:
    return data + b"\0" * (4 - len(data) % 4)   # always at least one zero, up to a multiple of 4


def encode_message(address: str, *values) -> bytes:
    """One OSC message. Supports str, bool, int and float values."""
    tags = ","
    body = b""
    for value in values:
        if isinstance(value, bool):
            tags += "T" if value else "F"
        elif isinstance(value, str):
            tags += "s"
            body += _padded(value.encode("utf-8"))
        elif isinstance(value, int):
            tags += "i"
            body += struct.pack(">i", value)
        elif isinstance(value, float):
            tags += "f"
            body += struct.pack(">f", value)
        else:
            raise TypeError(f"cannot send {type(value).__name__} over OSC")
    return _padded(address.encode("ascii")) + _padded(tags.encode("ascii")) + body


def fit(text: str, limit: int = MAX_CHARS) -> tuple[str, bool]:
    """The text as the chatbox will take it, and whether it had to be cut."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text, False
    return text[:limit - 1].rstrip() + "…", True


def fit_bilingual(translation: str, original: str) -> tuple[str, bool]:
    """Fit 'translation (original)', keeping room for both parts when either is long."""
    translation, original = (" ".join(text.split()) for text in (translation, original))
    if not translation or not original or translation == original:
        return fit(original or translation)
    budget = MAX_CHARS - 3   # space and parentheses
    translated_limit = min(len(translation), max(budget // 2, budget - len(original)))
    translation, translated_cut = fit(translation, translated_limit)
    original, original_cut = fit(original, budget - translated_limit)
    return f"{translation} ({original})", translated_cut or original_cut


def fit_lines(*texts: str) -> tuple[str, bool]:
    """Keep each nonempty, distinct language line within a shared OSC budget."""
    lines = list(dict.fromkeys(" ".join(text.split()) for text in texts if text.strip()))
    if not lines:
        return "", False
    budget = MAX_CHARS - (len(lines) - 1)
    lengths = [0] * len(lines)
    # Distribute space evenly, giving unused space from short lines to longer ones.
    while budget:
        pending = [i for i, line in enumerate(lines) if lengths[i] < len(line)]
        if not pending:
            break
        for i in pending:
            if not budget:
                break
            lengths[i] += 1
            budget -= 1
    fitted = [fit(line, length) for line, length in zip(lines, lengths)]
    return "\n".join(text for text, _ in fitted), any(cut for _, cut in fitted)


class Chatbox:
    def __init__(self, host: str = HOST, port: int = PORT):
        self._target = (host, port)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, text: str, sound: bool = False) -> None:
        """Show the text above the player's head now (the caller keeps MIN_GAP_S between calls)."""
        self._socket.sendto(encode_message("/chatbox/input", text, True, sound), self._target)

    def typing(self, on: bool) -> None:
        self._socket.sendto(encode_message("/chatbox/typing", on), self._target)

    def close(self) -> None:
        self._socket.close()


class TypingDots:
    """VRChat's "typing" dots, shown only for the first message after QUIET_S without one: they
    tell the others that something is coming. Messages after that replace each other directly.
    Safe to call from any thread."""

    def __init__(self, chatbox, clock=time.monotonic, quiet_s: float = QUIET_S):
        self._chatbox = chatbox
        self._clock = clock
        self._quiet_s = quiet_s
        self._lock = threading.Lock()
        self._last_message = float("-inf")
        self.on = False

    def starting(self) -> None:
        """A message is on its way (I started talking, or pressed Send)."""
        with self._lock:
            if not self.on and self._clock() - self._last_message >= self._quiet_s:
                self._show(True)

    def sent(self) -> None:
        """The message reached the chatbox: the dots go, and the quiet time starts again."""
        with self._lock:
            self._last_message = self._clock()
            if self.on:
                self._show(False)

    def cancelled(self) -> None:
        """Nothing will be sent after all (a cough, an empty sentence, a failed send). The next
        real message still counts as the first one."""
        with self._lock:
            if self.on:
                self._show(False)

    def _show(self, on: bool) -> None:
        self.on = on
        typing = getattr(self._chatbox, "typing", None)
        if typing is not None:
            try:
                typing(on)
            except OSError:
                pass      # VRChat closed: nothing to show the dots on
