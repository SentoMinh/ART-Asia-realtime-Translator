import hashlib
import threading
from contextlib import contextmanager

import pytest

from vrc import driver_setup


@pytest.mark.parametrize("error,expected", [(None, True), (FileNotFoundError, False), (PermissionError, None)])
def test_driver_registration_distinguishes_missing_from_failed_check(monkeypatch, error, expected):
    import sys
    from types import SimpleNamespace
    @contextmanager
    def open_key(root, path, reserved, flags):
        assert path == r"SYSTEM\CurrentControlSet\Services\VrctAudio"
        if error:
            raise error()
        yield object()
    monkeypatch.setitem(sys.modules, "winreg", SimpleNamespace(
        OpenKey=open_key, HKEY_LOCAL_MACHINE=1, KEY_READ=2, KEY_WOW64_64KEY=4))
    assert driver_setup.driver_registered() is expected


@pytest.mark.parametrize("corrupt,cancelled", [(True, False), (False, True)])
def test_bad_or_cancelled_download_never_launches_installer(monkeypatch, corrupt, cancelled):
    content = b"fake installer for verification tests"
    class Response:
        def raise_for_status(self): pass
        def iter_bytes(self): yield content
    @contextmanager
    def stream(*args, **kwargs): yield Response()
    monkeypatch.setattr(driver_setup.httpx, "stream", stream)
    monkeypatch.setattr(driver_setup.subprocess, "run", lambda *a, **kw: pytest.fail("Must not verify or launch"))
    manifest = dict(url="https://example.invalid/setup.exe", size=len(content),
                    sha256="0" * 64 if corrupt else hashlib.sha256(content).hexdigest())
    cancel = threading.Event()
    if cancelled:
        cancel.set()
        assert not driver_setup.download_and_install(manifest, cancel)
    else:
        with pytest.raises(driver_setup.DriverSetupError, match="verification"):
            driver_setup.download_and_install(manifest, cancel)


def test_invalid_signature_never_launches_installer(monkeypatch):
    content = b"unsigned installer"
    class Response:
        def raise_for_status(self): pass
        def iter_bytes(self): yield content
    @contextmanager
    def stream(*args, **kwargs): yield Response()
    monkeypatch.setattr(driver_setup.httpx, "stream", stream)
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        raise driver_setup.subprocess.CalledProcessError(1, args)
    monkeypatch.setattr(driver_setup.subprocess, "run", run)
    manifest = dict(url="https://example.invalid/setup.exe", size=len(content),
                    sha256=hashlib.sha256(content).hexdigest(), signer_thumbprint="A" * 40)
    with pytest.raises(driver_setup.subprocess.CalledProcessError):
        driver_setup.download_and_install(manifest, threading.Event())
    assert len(calls) == 1 and "Get-AuthenticodeSignature" in calls[0][-1]


@pytest.mark.parametrize("cancel_after_verify", [False, True])
def test_verified_installer_launches_only_if_not_cancelled(monkeypatch, cancel_after_verify):
    content = b"verified test installer"
    class Response:
        def raise_for_status(self): pass
        def iter_bytes(self): yield content
    @contextmanager
    def stream(*args, **kwargs): yield Response()
    monkeypatch.setattr(driver_setup.httpx, "stream", stream)
    cancel, calls = threading.Event(), []
    def run(args, **kwargs):
        calls.append(args[-1])
        assert kwargs["env"]["VRCT_DRIVER_SIGNER"] == "A" * 40
        if cancel_after_verify:
            cancel.set()
    monkeypatch.setattr(driver_setup.subprocess, "run", run)
    manifest = dict(url="https://example.invalid/setup.exe", size=len(content),
                    sha256=hashlib.sha256(content).hexdigest(), signer_thumbprint="A" * 40)
    assert driver_setup.download_and_install(manifest, cancel) is not cancel_after_verify
    assert "Get-AuthenticodeSignature" in calls[0]
    assert len(calls) == (1 if cancel_after_verify else 2)
    if not cancel_after_verify:
        assert "-Verb RunAs" in calls[1]
