"""Music sender for our installed microphone APO.

The endpoint must already have a validated APO installation. Calls belong to one
dedicated worker thread.
"""
from __future__ import annotations

import ctypes
from pathlib import Path
import threading
import uuid

import numpy as np


def probe(library: Path, endpoint_token: str) -> int:
    """0 absent, 1 host loaded, 2 audio callback active; never starts music."""
    dll = ctypes.CDLL(str(Path(library).resolve(strict=True)))
    dll.VrctProbe.argtypes = [ctypes.c_wchar_p, ctypes.c_int]
    dll.VrctProbe.restype = ctypes.c_uint32
    return dll.VrctProbe("{" + str(uuid.UUID(endpoint_token)) + "}", 0)


class ApoTransport:
    def __init__(self, library: Path, endpoint_token: str, *, local_test=False):
        self._owner = threading.get_ident()
        self._handle = None
        token = "{" + str(uuid.UUID(endpoint_token)) + "}"
        path = Path(library).resolve(strict=True)
        self._dll = ctypes.CDLL(str(path))
        self._dll.VrctOpen.argtypes = [ctypes.c_wchar_p, ctypes.c_int]
        self._dll.VrctOpen.restype = ctypes.c_void_p
        self._dll.VrctWrite.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float), ctypes.c_uint32]
        self._dll.VrctWrite.restype = ctypes.c_int
        self._dll.VrctClose.argtypes = [ctypes.c_void_p]
        self._dll.VrctClose.restype = ctypes.c_int
        self._handle = self._dll.VrctOpen(token, int(local_test))
        if not self._handle:
            raise RuntimeError("The microphone APO is not connected, or another music sender is already using it.")

    def _check_thread(self):
        if threading.get_ident() != self._owner:
            raise RuntimeError("Use the same worker thread to open, write and close the APO sender.")

    def write(self, samples, gain=1.0):
        """Send at most 100 ms of stereo float32 music at 48 kHz; never voice."""
        self._check_thread()
        if not self._handle:
            raise RuntimeError("The APO sender is closed.")
        data = np.asarray(samples, dtype=np.float32)
        if data.ndim != 2 or data.shape[1] != 2 or len(data) > 4800:
            raise ValueError("Music must be stereo with at most 4800 frames per write.")
        if not np.isfinite(gain) or not 0 <= gain <= 1:
            raise ValueError("Music gain must be between 0 and 1.")
        data = np.ascontiguousarray(np.clip(np.nan_to_num(data, nan=0, posinf=0, neginf=0) * gain, -1, 1))
        if not self._dll.VrctWrite(self._handle, data.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), len(data)):
            raise RuntimeError("The APO rejected the music buffer.")

    def close(self):
        self._check_thread()
        if self._handle:
            if not self._dll.VrctClose(self._handle):
                raise RuntimeError("Could not close the APO sender.")
            self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
