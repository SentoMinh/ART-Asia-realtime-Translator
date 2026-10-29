"""Conservative NVIDIA memory checks for local translation alongside a game."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

from . import local_model

RESERVE_MIB = 3072
PROBE_INTERVAL_S = 10.0
# Include CUDA context and decoding workspace above the quantized weights.
MODEL_MIB = {"nllb-200-ct2": 1536, "qwen3-1.7b-ct2": 3072}


def free_vram_mib() -> int | None:
    """Only one physical, unremapped GPU can be matched safely to CUDA device zero."""
    if os.environ.get("CUDA_VISIBLE_DEVICES", "0").strip() != "0":
        return None
    executable = shutil.which("nvidia-smi")
    if not executable:
        return None
    try:
        result = subprocess.run(
            [executable, "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True, timeout=1.0,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        rows = result.stdout.strip().splitlines()
        if len(rows) != 1:
            return None
        free = int(rows[0].strip())
        return free if free >= 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def cublas_available() -> bool:
    folders = [Path(folder) for folder in local_model.gpu_folders()]
    folders.extend(Path(folder) for folder in os.environ.get("PATH", "").split(os.pathsep) if folder)
    return all(any((folder / name).is_file() for folder in folders)
               for name in ("cublas64_12.dll", "cublasLt64_12.dll"))


def select_device(runtime, model_id: str) -> tuple[str, str]:
    mode = os.environ.get("VRCT_LOCAL_DEVICE", "auto").strip().lower()
    if mode != "auto":
        return "cpu", "CPU requested" if mode == "cpu" else "unknown VRCT_LOCAL_DEVICE value"
    if os.environ.get("CUDA_VISIBLE_DEVICES", "0").strip() != "0":
        return "cpu", "CUDA device mapping cannot be verified"
    if not cublas_available():
        return "cpu", "cuBLAS libraries are unavailable"
    try:
        if runtime.get_cuda_device_count() != 1:
            return "cpu", "requires one CUDA device"
        if "int8_float16" not in runtime.get_supported_compute_types("cuda"):
            return "cpu", "CUDA int8_float16 is unavailable"
    except Exception:
        return "cpu", "CUDA capability could not be checked"
    free = free_vram_mib()
    required = MODEL_MIB.get(model_id)
    if free is None or required is None:
        return "cpu", "free GPU memory could not be verified"
    if free < required + RESERVE_MIB:
        return "cpu", f"{free} MiB free; need {required + RESERVE_MIB} MiB including game reserve"
    return "cuda", f"{free} MiB free; reserving {RESERVE_MIB} MiB for the game"
