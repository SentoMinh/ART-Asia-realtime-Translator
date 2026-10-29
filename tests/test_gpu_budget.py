"""Gaming GPU decisions use fake telemetry and fake runtimes; no CUDA models are started."""
from types import SimpleNamespace
import subprocess
import sys

import pytest

from engine import gpu_budget, local_inference, local_model
from vrc.translate import TranslateError


@pytest.fixture
def telemetry(monkeypatch):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    monkeypatch.delenv("VRCT_LOCAL_DEVICE", raising=False)
    monkeypatch.setattr(gpu_budget.shutil, "which", lambda name: "nvidia-smi.exe")
    state = {"output": "8192\n", "calls": []}

    def run(command, **options):
        state["calls"].append((command, options))
        if isinstance(state["output"], Exception):
            raise state["output"]
        return SimpleNamespace(stdout=state["output"])

    monkeypatch.setattr(gpu_budget.subprocess, "run", run)
    return state


@pytest.mark.parametrize("output,expected", [
    ("8192\n", 8192), (" 4096 \n", 4096), ("0\n", 0),
    ("8192\n8192\n", None), ("N/A\n", None), ("", None), ("-1\n", None),
    (OSError("missing"), None), (subprocess.TimeoutExpired("nvidia-smi", 1), None),
])
def test_only_valid_single_card_memory_is_trusted(telemetry, output, expected):
    telemetry["output"] = output
    assert gpu_budget.free_vram_mib() == expected
    command, options = telemetry["calls"][0]
    assert command[1:] == ["--query-gpu=memory.free", "--format=csv,noheader,nounits"]
    assert options["timeout"] == 1.0 and options["check"]
    assert options["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)


@pytest.mark.parametrize("mapping", ["", "1", "0,1", "GPU-some-uuid"])
def test_remapped_or_disabled_cuda_never_probes_an_unmatched_card(telemetry, monkeypatch, mapping):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", mapping)
    assert gpu_budget.free_vram_mib() is None
    assert gpu_budget.select_device(object(), "nllb-200-ct2")[0] == "cpu"
    assert not telemetry["calls"]


def test_missing_nvidia_smi_is_unknown_memory(telemetry, monkeypatch):
    monkeypatch.setattr(gpu_budget.shutil, "which", lambda name: None)
    assert gpu_budget.free_vram_mib() is None
    assert not telemetry["calls"]


def test_both_cublas_libraries_must_exist(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(local_model, "gpu_folders", lambda: [str(tmp_path)])
    assert not gpu_budget.cublas_available()
    (tmp_path / "cublas64_12.dll").touch()
    assert not gpu_budget.cublas_available()
    (tmp_path / "cublasLt64_12.dll").touch()
    assert gpu_budget.cublas_available()


@pytest.mark.parametrize("model,free,device", [
    ("nllb-200-ct2", 4608, "cuda"), ("nllb-200-ct2", 4607, "cpu"),
    ("qwen3-1.7b-ct2", 6144, "cuda"), ("qwen3-1.7b-ct2", 6143, "cpu"),
    ("unknown", 8192, "cpu"), ("nllb-200-ct2", None, "cpu"),
])
def test_model_memory_and_game_reserve_are_required(telemetry, monkeypatch, model, free, device):
    monkeypatch.setattr(gpu_budget, "cublas_available", lambda: True)
    monkeypatch.setattr(gpu_budget, "free_vram_mib", lambda: free)
    runtime = SimpleNamespace(get_cuda_device_count=lambda: 1,
                              get_supported_compute_types=lambda device: {"int8_float16"})
    assert gpu_budget.select_device(runtime, model)[0] == device


@pytest.mark.parametrize("libraries,count,types", [
    (False, 1, {"int8_float16"}), (True, 0, {"int8_float16"}),
    (True, 2, {"int8_float16"}), (True, 1, {"float32"}),
])
def test_missing_runtime_capability_uses_cpu_without_memory_probe(telemetry, monkeypatch, libraries, count, types):
    monkeypatch.setattr(gpu_budget, "cublas_available", lambda: libraries)
    runtime = SimpleNamespace(get_cuda_device_count=lambda: count,
                              get_supported_compute_types=lambda device: types)
    assert gpu_budget.select_device(runtime, "nllb-200-ct2")[0] == "cpu"
    assert not telemetry["calls"]


@pytest.mark.parametrize("mode", ["cpu", "invalid"])
def test_explicit_cpu_or_invalid_setting_never_uses_gpu(telemetry, monkeypatch, mode):
    monkeypatch.setenv("VRCT_LOCAL_DEVICE", mode)
    assert gpu_budget.select_device(object(), "nllb-200-ct2")[0] == "cpu"
    assert not telemetry["calls"]


@pytest.fixture
def fake_models(monkeypatch, tmp_path):
    state = {"creates": [], "unloaded": [], "libraries": [], "load_error": False, "inference_error": ""}
    monkeypatch.setenv("VRCT_CPU_THREADS", "1")
    monkeypatch.setattr(local_model, "missing", lambda model: "")
    monkeypatch.setattr(local_model, "model_folder", lambda model: tmp_path / model)
    monkeypatch.setattr(gpu_budget, "select_device", lambda runtime, model: ("cuda", "test GPU budget"))
    monkeypatch.setattr(gpu_budget, "free_vram_mib", lambda: 8192)
    monkeypatch.setattr(local_inference.stt, "_add_gpu_libraries", lambda: state["libraries"].append(True))

    def create(root, **options):
        state["creates"].append(options)
        device = options["device"]
        if device == "cuda" and state["load_error"]:
            raise RuntimeError("CUDA allocation failed")

        def infer(*args, **kwargs):
            if device == "cuda" and state["inference_error"]:
                raise RuntimeError(state["inference_error"])
            return [SimpleNamespace(hypotheses=[["vie_Latn", "Xin", "chao", "</s>"]],
                                    sequences=[["Xin", "chao", "<|im_end|>"]])]

        return SimpleNamespace(translate_batch=infer, generate_batch=infer,
                               unload_model=lambda: state["unloaded"].append(device))

    tokenizer = SimpleNamespace(encode=lambda text, **kwargs: SimpleNamespace(tokens=text.split()),
                                token_to_id=lambda token: token,
                                decode=lambda tokens, **kwargs: " ".join(t for t in tokens if t != "</s>"))
    monkeypatch.setitem(sys.modules, "ctranslate2", SimpleNamespace(Translator=create, Generator=create))
    monkeypatch.setitem(sys.modules, "tokenizers", SimpleNamespace(
        Tokenizer=SimpleNamespace(from_file=lambda path: tokenizer)))
    monkeypatch.setattr(local_inference, "translator", local_inference.LocalTranslator())
    monkeypatch.setattr(local_inference, "qwen_translator", local_inference.LocalQwenTranslator())
    monkeypatch.setattr(local_inference, "hy_mt_translator", local_inference.LocalHyMTTranslator())
    return state


@pytest.mark.parametrize("kind", ["translator", "qwen_translator"])
def test_translation_uses_budgeted_gpu_once_with_one_cpu_thread(fake_models, kind):
    engine = getattr(local_inference, kind)
    assert engine.translate("Hello", "vi", "en") == "Xin chao"
    assert engine.translate("Hello again", "vi", "en") == "Xin chao"
    assert fake_models["creates"] == [dict(device="cuda", compute_type="int8_float16",
                                           inter_threads=1, intra_threads=1)]
    assert fake_models["libraries"] == [True]


@pytest.mark.parametrize("kind", ["translator", "qwen_translator"])
def test_gpu_load_failure_falls_back_to_cpu_without_repeated_gpu_loading(fake_models, kind):
    fake_models["load_error"] = True
    engine = getattr(local_inference, kind)
    assert engine.translate("Hello", "vi", "en") == "Xin chao"
    assert engine.translate("Hello again", "vi", "en") == "Xin chao"
    assert [call["device"] for call in fake_models["creates"]] == ["cuda", "cpu"]
    local_inference.release_local_translation()
    assert engine.translate("Hello after release", "vi", "en") == "Xin chao"
    assert [call["device"] for call in fake_models["creates"]] == ["cuda", "cpu", "cpu"]


@pytest.mark.parametrize("free", [3071, None])
def test_memory_pressure_unloads_gpu_once_and_keeps_cpu_until_model_switch(fake_models, monkeypatch, free):
    engine = local_inference.translator
    assert engine.translate("Hello", "vi", "en") == "Xin chao"
    engine._gpu_checked_at = float("-inf")
    monkeypatch.setattr(gpu_budget, "free_vram_mib", lambda: free)
    assert engine.translate("Under pressure", "vi", "en") == "Xin chao"
    assert fake_models["unloaded"] == ["cuda"]
    monkeypatch.setattr(gpu_budget, "free_vram_mib", lambda: 8192)
    assert engine.translate("Memory returned", "vi", "en") == "Xin chao"
    assert [call["device"] for call in fake_models["creates"]] == ["cuda", "cpu"]
    local_inference.qwen_translator.translate("Another model", "vi", "en")
    engine.translate("Back to NLLB", "vi", "en")
    assert [call["device"] for call in fake_models["creates"]] == ["cuda", "cpu", "cuda", "cuda"]


def test_active_gpu_memory_probe_runs_at_most_once_per_ten_seconds(fake_models, monkeypatch):
    clock, probes = [100.0], []
    monkeypatch.setattr(local_inference.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(gpu_budget, "free_vram_mib", lambda: probes.append(clock[0]) or 8192)
    engine = local_inference.translator
    engine.translate("Hello", "vi", "en")
    for now in (100, 101, 109.9, 110, 111, 119.9, 120):
        clock[0] = now
        engine.translate("Next", "vi", "en")
    assert probes == [100, 110, 120]


@pytest.mark.parametrize("free", [3071, None])
def test_gpu_load_rechecks_actual_reserve_before_first_inference(fake_models, monkeypatch, free):
    monkeypatch.setattr(gpu_budget, "free_vram_mib", lambda: free)
    engine = local_inference.translator
    assert engine.translate("Hello", "vi", "en") == "Xin chao"
    assert fake_models["unloaded"] == ["cuda"]
    assert [call["device"] for call in fake_models["creates"]] == ["cuda", "cpu"]
    assert engine._device == "cpu"


def test_idle_gpu_pressure_releases_weights_without_loading_cpu(fake_models, monkeypatch):
    engine = local_inference.translator
    engine.translate("Hello", "vi", "en")
    engine._gpu_checked_at = float("-inf")
    probes = []
    monkeypatch.setattr(gpu_budget, "free_vram_mib", lambda: probes.append(True) or 1000)
    with local_inference._translation_lock:
        local_inference.check_local_gpu_budget()
    assert not probes
    assert engine._device == "cuda"
    local_inference.check_local_gpu_budget()
    assert probes == [True]
    assert engine._model is None
    assert fake_models["unloaded"] == ["cuda"]
    assert [call["device"] for call in fake_models["creates"]] == ["cuda"]


def test_release_rechecks_provider_under_translation_lock(fake_models):
    engine = local_inference.translator
    engine.translate("Hello", "vi", "en")
    checked = []

    def still_online():
        checked.append(local_inference._translation_lock.locked())
        return False

    assert not local_inference.release_local_translation(still_online)
    assert checked == [True]
    assert engine._model is not None
    assert not fake_models["unloaded"]


@pytest.mark.parametrize("kind", ["translator", "qwen_translator"])
def test_runtime_oom_releases_gpu_and_next_line_uses_cpu(fake_models, kind):
    fake_models["inference_error"] = "CUDA failed with error out of memory"
    engine = getattr(local_inference, kind)
    with pytest.raises(TranslateError, match="out of memory") as caught:
        engine.translate("Hello", "vi", "en")
    assert caught.value.wait == 0
    assert fake_models["unloaded"] == ["cuda"] and engine._model is None
    assert engine.translate("Next line", "vi", "en") == "Xin chao"
    assert [call["device"] for call in fake_models["creates"]] == ["cuda", "cpu"]
