import ctypes
import threading

import numpy as np
import pytest

from vrc import apo_transport


class Function:
    def __init__(self, action): self.action = action
    def __call__(self, *args): return self.action(*args)


@pytest.fixture
def library(tmp_path, monkeypatch):
    samples, closes = [], []
    class Library:
        VrctOpen = Function(lambda *args: 123)
        VrctWrite = Function(lambda handle, ptr, count: samples.append(
            np.ctypeslib.as_array(ptr, shape=(count * 2,)).copy()) or 1)
        VrctClose = Function(lambda handle: closes.append(handle) or 1)
    monkeypatch.setattr(ctypes, "CDLL", lambda path: Library())
    path = tmp_path / "producer.dll"
    path.touch()
    return path, samples, closes


def test_sender_applies_gain_sanitizes_and_closes(library):
    path, samples, closes = library
    with apo_transport.ApoTransport(path, "{512d15b9-38ae-42c4-9747-abb988252121}") as sender:
        sender.write([[.8, -.4], [float("nan"), float("inf")]], gain=.5)
    np.testing.assert_allclose(samples[0], [.4, -.2, 0, 0])
    assert closes == [123]
    with pytest.raises(RuntimeError, match="closed"):
        sender.write([[0, 0]])


def test_sender_rejects_bad_format_and_cross_thread_use(library):
    path, samples, _ = library
    with apo_transport.ApoTransport(path, "{512d15b9-38ae-42c4-9747-abb988252121}") as sender:
        for bad in ([1, 2], [[1, 2, 3]], np.zeros((4801, 2))):
            with pytest.raises(ValueError): sender.write(bad)
        errors = []
        def worker():
            try: sender.write([[1, 1]])
            except RuntimeError as error: errors.append(str(error))
        thread = threading.Thread(target=worker)
        thread.start(); thread.join()
        assert len(errors) == 1 and "same worker" in errors[0]
    assert not samples
