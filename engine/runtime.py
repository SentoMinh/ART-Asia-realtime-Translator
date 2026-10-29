"""Small CPU budgets for a translator that runs beside a game."""
from __future__ import annotations

import logging
import os
import sys


def cpu_threads() -> int:
    """One inference thread by default; an explicit override may use two."""
    try:
        return max(1, min(2, int(os.environ.get("VRCT_CPU_THREADS", "1"))))
    except ValueError:
        return 1


def configure_native_threads() -> None:
    """Call before importing NumPy/model runtimes; leave explicit user overrides alone."""
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ.setdefault(name, str(cpu_threads()))
    os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
    os.environ.setdefault("KMP_BLOCKTIME", "0")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def prefer_game_cpu() -> bool:
    """Let normal-priority game threads run ahead of ART under CPU contention.

    This changes only this process, with no affinity restriction or system-wide setting.
    A normal-priority opt-out is available for diagnosing audio/translation delays.

    This is a gaming tradeoff, not a measured speed win: the 1.0.5 whole-app replay found
    lower translation throughput under CPU saturation. It was not re-benchmarked here.
    """
    if sys.platform != "win32" or os.environ.get("VRCT_PROCESS_PRIORITY", "").lower() == "normal":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.SetPriorityClass.restype = wintypes.BOOL
        if not kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x00004000):  # BELOW_NORMAL_PRIORITY_CLASS
            raise ctypes.WinError(ctypes.get_last_error())
        return True
    except (AttributeError, OSError) as error:
        logging.getLogger(__name__).warning("could not lower translator CPU priority: %s", error)
        return False
