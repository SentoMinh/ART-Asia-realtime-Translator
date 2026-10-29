"""Gaming CPU policy, without changing the test runner's scheduling priority."""
from types import SimpleNamespace

import pytest

from engine import runtime


@pytest.mark.parametrize("value,expected", [(None, 1), ("invalid", 1), ("0", 1), ("-4", 1), ("2", 2), ("64", 2)])
def test_inference_threads_are_bounded(monkeypatch, value, expected):
    monkeypatch.delenv("VRCT_CPU_THREADS", raising=False)
    if value is not None:
        monkeypatch.setenv("VRCT_CPU_THREADS", value)
    assert runtime.cpu_threads() == expected


def test_native_pools_sleep_and_respect_explicit_overrides(monkeypatch):
    names = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS",
             "OMP_WAIT_POLICY", "KMP_BLOCKTIME", "TOKENIZERS_PARALLELISM", "VRCT_CPU_THREADS")
    for name in names:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MKL_NUM_THREADS", "2")
    runtime.configure_native_threads()
    assert runtime.os.environ["OMP_NUM_THREADS"] == "1"
    assert runtime.os.environ["MKL_NUM_THREADS"] == "2"
    assert runtime.os.environ["OMP_WAIT_POLICY"] == "PASSIVE"
    assert runtime.os.environ["KMP_BLOCKTIME"] == "0"
    assert runtime.os.environ["TOKENIZERS_PARALLELISM"] == "false"


def test_windows_priority_only_targets_current_process(monkeypatch):
    import ctypes
    calls = []
    def current():
        return 321
    def priority(handle, value):
        calls.append((handle, value))
        return True
    monkeypatch.setattr(runtime.sys, "platform", "win32")
    monkeypatch.delenv("VRCT_PROCESS_PRIORITY", raising=False)
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **kw: SimpleNamespace(
        GetCurrentProcess=current, SetPriorityClass=priority), raising=False)
    assert runtime.prefer_game_cpu() is True
    assert calls == [(321, 0x4000)]
    monkeypatch.setenv("VRCT_PROCESS_PRIORITY", "normal")
    assert runtime.prefer_game_cpu() is False
    assert len(calls) == 1


def test_priority_failure_does_not_prevent_launch(monkeypatch):
    import ctypes
    monkeypatch.setattr(runtime.sys, "platform", "win32")
    monkeypatch.delenv("VRCT_PROCESS_PRIORITY", raising=False)
    def unavailable(*a, **kw):
        raise OSError("not available")
    monkeypatch.setattr(ctypes, "WinDLL", unavailable, raising=False)
    assert runtime.prefer_game_cpu() is False


def test_gpu_whisper_caps_host_threads_without_changing_decode_quality(monkeypatch):
    from engine import stt
    calls = []
    monkeypatch.delenv("VRCT_CPU_THREADS", raising=False)
    monkeypatch.setattr(stt.local_model, "missing", lambda *a: "")
    monkeypatch.setattr(stt.local_model, "ready", lambda **kw: True)
    monkeypatch.setattr(stt, "_add_gpu_libraries", lambda: None)
    def model(source, **options):
        calls.append(options)
        return SimpleNamespace(transcribe=lambda *a, **kw: ([], None))
    monkeypatch.setattr(stt, "whisper_class", lambda: model)
    stt.LocalWhisper().load()
    assert calls == [dict(device="cuda", compute_type="float16", cpu_threads=1, num_workers=1)]


def test_cuda_directories_are_kept_alive_without_path_growth(monkeypatch, tmp_path):
    from engine import stt
    folder = str(tmp_path)
    handles = []
    def add(path):
        handle = object()
        handles.append((path, handle))
        return handle
    monkeypatch.setattr(stt, "_gpu_dll_handles", {})
    monkeypatch.setattr(stt.local_model, "gpu_folders", lambda: [folder])
    monkeypatch.setattr(stt.os, "add_dll_directory", add, raising=False)
    monkeypatch.setenv("PATH", "existing")
    stt._add_gpu_libraries()
    stt._add_gpu_libraries()
    assert len(handles) == 1
    assert stt._gpu_dll_handles[folder] is handles[0][1]
    assert stt.os.environ["PATH"].split(stt.os.pathsep) == [folder, "existing"]


@pytest.mark.parametrize("hearing,enabled", [("local", False), ("openai", True)])
def test_startup_applies_saved_settings_before_attaching_speech(monkeypatch, hearing, enabled):
    from ui import main, service_health
    from ui.config import Settings
    from vr import main as vr_main

    saved = Settings(hearing=hearing, translating="openai", mic_on=enabled, subtitles_on=enabled)
    events = []
    noop = lambda *args: None
    app = SimpleNamespace(aboutToQuit=SimpleNamespace(connect=noop), setApplicationName=noop,
                          setWindowIcon=noop, setStyleSheet=noop, exec=lambda: 7)

    class FakeLiveBackend:
        def apply_settings(self, settings):
            self.settings = settings
            events.append("apply")

        def start(self):
            events.append("start")

        def stop(self):
            events.append("stop")

    def load():
        events.append("load")
        return saved

    def attach(backend):
        assert backend.settings is saved
        assert (backend.settings.hearing, backend.settings.mic_on, backend.settings.subtitles_on) == (
            hearing, enabled, enabled)
        events.append("attach")

    def window(backend, settings):
        assert backend.settings is settings is saved
        events.append("window")
        return SimpleNamespace(show=noop, show_update_notice=noop)

    monkeypatch.setattr(runtime, "prefer_game_cpu", noop)
    monkeypatch.setattr(main, "_own_taskbar_button", noop)
    monkeypatch.setattr(main, "program_icon", noop)
    monkeypatch.setattr(main, "QApplication", SimpleNamespace(instance=lambda: app))
    monkeypatch.setattr(main, "QTimer", SimpleNamespace(singleShot=noop))
    monkeypatch.setattr(main.sys, "argv", ["translator"])
    monkeypatch.setattr(main.config, "load", load)
    monkeypatch.setattr(main, "LiveBackend", FakeLiveBackend)
    monkeypatch.setattr(main, "speech_translator", lambda pick, **kw: pick())
    monkeypatch.setattr(main, "attach_speech", attach)
    monkeypatch.setattr(main, "MainWindow", window)
    monkeypatch.setattr(main, "look_for_update", noop)
    monkeypatch.setattr(service_health, "ServiceHealth", lambda backend: SimpleNamespace(start=noop, stop=noop))
    monkeypatch.setattr(vr_main, "attach_wrist", lambda window: SimpleNamespace(start=noop, stop=noop))

    assert main.run() == 7
    assert events == ["load", "apply", "attach", "window", "start", "stop"]
