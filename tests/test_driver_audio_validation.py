import numpy as np
import pytest

from driver.validate_audio import analyze, select_device, test_signal as make_signal


def test_detects_delayed_stereo_signal_and_stop_silence():
    source = make_signal()
    recording = np.concatenate((np.zeros((500, 2)), source, np.zeros((15000, 2))))
    result = analyze(source, recording)
    assert result["passed"]
    assert result["offset_frames"] == 500


@pytest.mark.parametrize("fault", ["silence", "swapped", "lost_frames", "stale_tail"])
def test_rejects_broken_audio_paths(fault):
    source = make_signal()
    damaged = source.copy()
    tail = np.zeros((15000, 2))
    if fault == "silence": damaged[:] = 0
    if fault == "swapped": damaged = damaged[:, ::-1]
    if fault == "lost_frames": damaged[10000:11000] = 0
    if fault == "stale_tail": tail[:] = 0.02
    assert not analyze(source, np.concatenate((damaged, tail)))["passed"]


def test_device_selection_never_uses_default_or_ambiguous_endpoint():
    apis = [{"name": "Windows WASAPI"}]
    device = {"name": "VRChat Translator Mix", "max_output_channels": 2, "hostapi": 0}
    assert select_device([device], apis, "VRChat Translator Mix", "output") == 0
    for devices in ([], [device, device], [{**device, "name": "Speakers"}]):
        with pytest.raises(RuntimeError, match="No fallback"):
            select_device(devices, apis, "VRChat Translator Mix", "output")
