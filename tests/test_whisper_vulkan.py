from types import SimpleNamespace

import numpy as np
import pytest

from engine import local_inference, local_model, whisper_vulkan
from engine.stt import SttError


class Native:
    def __init__(self):
        self.opens = self.frees = 0
        self.calls = []
        self.result = 0
        self.language = b"en"
        self.segments = [(b"Hello there.", 0.05, -0.2)]

    def art_whisper_open(self, path):
        assert path.endswith("whisper-vulkan\\model.bin") or path.endswith("whisper-vulkan/model.bin")
        self.opens += 1
        return 123

    def art_whisper_run(self, context, audio, count, lang):
        assert context == 123
        self.calls.append((count, lang))
        return self.result

    def art_whisper_free(self, context):
        assert context == 123
        self.frees += 1

    def art_whisper_error(self): return b"Vulkan GPU out of memory"
    def art_whisper_device(self, context): return b"Test Radeon"
    def art_whisper_language(self, context): return self.language
    def art_whisper_segments(self, context): return len(self.segments)
    def art_whisper_text(self, context, i): return self.segments[i][0]
    def art_whisper_no_speech(self, context, i): return self.segments[i][1]
    def art_whisper_logprob(self, context, i): return self.segments[i][2]


@pytest.fixture
def native(monkeypatch):
    dll = Native()
    monkeypatch.setattr(whisper_vulkan, "library", lambda: dll)
    monkeypatch.setattr(local_model, "missing", lambda model: "")
    return dll


def test_model_reused_and_released_on_switch_without_cuda(native, monkeypatch):
    monkeypatch.setattr(local_inference, "LocalSenseVoice", lambda: SimpleNamespace(load=lambda: None))
    local_model.select(whisper_vulkan.MODEL)
    hearing = local_inference.LocalHearing()
    for _ in range(2):
        assert hearing.transcribe(np.zeros(16000), "en").text == "Hello there."
    assert native.opens == 1 and native.calls == [(16000, b"en")] * 3  # One startup warmup.
    local_model.select("sensevoice")
    hearing.load()
    assert native.frees == 1
    assert local_model.selected("translating") == "nllb-200-ct2"


def test_vulkan_errors_are_visible_and_do_not_switch_to_other_models(native):
    engine = whisper_vulkan.VulkanWhisper()
    engine.load()
    native.result = 1
    with pytest.raises(SttError, match="Vulkan GPU out of memory"):
        engine.transcribe(np.zeros(16000), "en")
    native.result = 0
    assert engine.transcribe(np.zeros(16000), "en").text
    engine.close()
    engine.close()
    assert native.frees == 1


def test_filters_silence_repetition_and_known_phantoms(native):
    engine = whisper_vulkan.VulkanWhisper()
    native.segments = [(b"noisy", .9, -2), (b"you a give " * 100, .1, -.1), (b"A real sentence.", .1, -.1)]
    assert engine.transcribe(np.zeros(16000), None).text == "A real sentence."
    native.segments = [(b"Thanks for watching", .1, -.1)]
    assert not engine.transcribe(np.zeros(16000), None).text
    engine.close()


def test_chinese_detection_and_forced_language(native):
    engine = whisper_vulkan.VulkanWhisper()
    engine.load()
    native.calls.clear()
    engine.transcribe(np.zeros(16000), "zh")
    assert [call[1] for call in native.calls] == [None, b"zh"]
    native.calls.clear()
    native.language = b"yue"
    assert engine.transcribe(np.zeros(16000), "zh").lang == "yue"
    assert [call[1] for call in native.calls] == [None]
    engine.close()


def test_bad_audio_and_missing_files_do_not_enter_native_code(native, monkeypatch):
    engine = whisper_vulkan.VulkanWhisper()
    assert not engine.transcribe([], "en").text
    for audio in ([float("nan")], [[1, 2]]):
        with pytest.raises(SttError, match="mono speech"):
            engine.transcribe(audio, "en")
    monkeypatch.setattr(local_model, "missing", lambda model: "download first")
    with pytest.raises(SttError, match="download first"):
        engine.transcribe(np.zeros(16000), "en")
    assert not native.opens


def test_vulkan_has_own_pinned_model_and_needs_no_nvidia(monkeypatch):
    model = whisper_vulkan.MODEL
    monkeypatch.setattr(local_model, "installed", lambda model: True)
    monkeypatch.setattr(local_model, "nvidia_card", lambda: pytest.fail("Vulkan must not require CUDA"))
    assert "not downloaded" in local_model.missing(model)
    monkeypatch.setattr(local_model, "ready", lambda **kw: True)
    assert local_model.missing(model) == ""
    (part,) = local_model.parts(model)
    assert part.place == "whisper-vulkan/model.bin"
    assert part.size == 574041195 and len(part.sha256) == 64


def test_vulkan_runtime_presence_is_separate_from_cuda(tmp_path, monkeypatch):
    path = tmp_path / "art_whisper_vulkan.dll"
    monkeypatch.setattr(whisper_vulkan, "runtime_file", lambda: path)
    assert not local_model.installed(whisper_vulkan.MODEL)
    path.write_bytes(b"runtime")
    assert local_model.installed(whisper_vulkan.MODEL)
