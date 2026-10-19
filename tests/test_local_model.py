"""The Local Model's download: checked, picked up again where it broke off, and only the files
the model loads are kept. A pretend server stands in for PyPI and Hugging Face."""
import hashlib
import io
import sys
import zipfile
from collections import namedtuple
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from engine import local_model
from engine.local_model import DownloadError, Part, Stopped

BASE = "https://files.test/"


class Stream:
    def __init__(self, status, data, breaks_after=None):
        self.status_code, self._data, self._breaks_after = status, data, breaks_after

    def __enter__(self):
        return self

    def __exit__(self, *error):
        return False

    def iter_bytes(self, size):
        for start in range(0, len(self._data), size):
            if self._breaks_after is not None and start >= self._breaks_after:
                raise ConnectionError("connection reset")
            yield self._data[start:start + size]


class Http:
    """It knows the Range header. `breaks`: after how many bytes each answer's connection
    breaks, answer by answer (none left = it sends everything)."""

    def __init__(self, files, breaks=(), ranges=True):
        self.files, self.breaks, self.ranges, self.asked = files, list(breaks), ranges, []

    def stream(self, method, url, headers=None):
        start = int((headers or {}).get("Range", "bytes=0-")[6:-1])
        self.asked.append((url.removeprefix(BASE), start))
        if url not in self.files:
            return Stream(404, b"")
        breaks_after = self.breaks.pop(0) if self.breaks else None
        if start and self.ranges:
            return Stream(206, self.files[url][start:], breaks_after)
        return Stream(200, self.files[url], breaks_after)


@pytest.fixture
def served(monkeypatch):
    """A small zip, of which two files are wanted, and a plain file stand in for the real 2 GB."""
    wheel = io.BytesIO()
    with zipfile.ZipFile(wheel, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("nvidia/bin/a.dll", b"A" * 30)
        archive.writestr("nvidia/bin/b.dll", b"B" * 50)
        archive.writestr("nvidia/include/unused.h", b"not needed")
    files = {BASE + "gpu.whl": wheel.getvalue(), BASE + "model.bin": bytes(range(200))}

    def sha256(name):
        return hashlib.sha256(files[BASE + name]).hexdigest()
    monkeypatch.setattr(local_model, "PARTS", (
        Part(BASE + "gpu.whl", len(files[BASE + "gpu.whl"]), sha256("gpu.whl"),
             unzip=(("nvidia/bin/a.dll", "gpu/a.dll", 30), ("nvidia/bin/b.dll", "gpu/b.dll", 50))),
        Part(BASE + "model.bin", 200, sha256("model.bin"), "whisper/model.bin")))
    monkeypatch.setattr(local_model, "BLOCK", 16)
    return files


def test_everything_is_downloaded_checked_and_put_in_place(served, tmp_path):
    seen = []
    local_model.download(progress=lambda done, total: seen.append((done, total)),
                         http=Http(served), root=tmp_path)
    assert local_model.ready(tmp_path)
    assert (tmp_path / "gpu" / "a.dll").read_bytes() == b"A" * 30
    assert (tmp_path / "whisper" / "model.bin").read_bytes() == served[BASE + "model.bin"]
    # the zip itself and the rest of what it held are gone
    assert sorted(path.name for path in tmp_path.rglob("*") if path.is_file()) == ["a.dll", "b.dll", "model.bin"]
    total = local_model.size()
    assert seen[-1] == (total, total) and [done for done, _ in seen] == sorted(done for done, _ in seen)


def test_what_is_there_is_not_downloaded_again(served, tmp_path):
    local_model.download(http=Http(served), root=tmp_path)
    (tmp_path / "whisper" / "model.bin").unlink()
    http = Http(served)
    local_model.download(http=http, root=tmp_path)
    assert http.asked == [("model.bin", 0)] and local_model.ready(tmp_path)


def test_a_download_that_broke_off_continues_where_it_stopped(served, tmp_path):
    waiting = tmp_path / local_model.WAITING
    waiting.mkdir()
    (waiting / "model.bin").write_bytes(served[BASE + "model.bin"][:120])
    assert local_model.arrived(tmp_path) == 120
    http = Http(served)
    local_model.download(http=http, root=tmp_path)
    assert ("model.bin", 120) in http.asked and local_model.ready(tmp_path)


def test_a_broken_connection_is_picked_up_again(served, tmp_path):
    waits = []
    http = Http(served, breaks=[32])             # the first answer stops after 32 bytes
    local_model.download(http=http, root=tmp_path, wait=waits.append)
    assert http.asked[:2] == [("gpu.whl", 0), ("gpu.whl", 32)] and waits == [2]
    assert local_model.ready(tmp_path)


def test_a_server_that_cannot_continue_sends_everything_again(served, tmp_path):
    http = Http(served, breaks=[32], ranges=False)
    local_model.download(http=http, root=tmp_path, wait=lambda seconds: None)
    assert local_model.ready(tmp_path)


def test_a_connection_that_keeps_breaking_ends_with_the_reason(served, tmp_path):
    http = Http(served, breaks=[0] * 99)
    with pytest.raises(DownloadError, match=r"files\.test keeps breaking \(connection reset\)"):
        local_model.download(http=http, root=tmp_path, wait=lambda seconds: None)
    assert len(http.asked) == local_model.TRIES


def test_a_refused_download_names_the_server(served, tmp_path):
    del served[BASE + "gpu.whl"]
    with pytest.raises(DownloadError, match=r"files\.test refused the download \(error 404\)"):
        local_model.download(http=Http(served), root=tmp_path)


def test_a_damaged_download_is_thrown_away(served, tmp_path):
    served[BASE + "model.bin"] = bytes(200)      # the right size, the wrong contents
    with pytest.raises(DownloadError, match="model.bin arrived damaged"):
        local_model.download(http=Http(served), root=tmp_path)
    assert not local_model.ready(tmp_path)
    assert not (tmp_path / local_model.WAITING / "model.bin").exists()
    assert (tmp_path / "gpu" / "a.dll").exists()         # the part that was fine stays


def test_stopping_keeps_what_arrived(served, tmp_path):
    seen = []
    with pytest.raises(Stopped):
        local_model.download(progress=lambda done, total: seen.append(done), stop=lambda: len(seen) >= 2,
                             http=Http(served), root=tmp_path)
    assert 0 < local_model.arrived(tmp_path) < local_model.size()


def test_too_little_room_on_the_disk_is_said_before_anything_is_downloaded(served, tmp_path, monkeypatch):
    monkeypatch.setattr(local_model.shutil, "disk_usage", lambda path: namedtuple("Usage", "free")(100))
    http = Http(served)
    with pytest.raises(DownloadError, match="not enough free space"):
        local_model.download(http=http, root=tmp_path)
    assert http.asked == []


def test_what_the_local_model_lacks_is_said_in_plain_words(monkeypatch):
    monkeypatch.setattr(local_model, "installed", lambda model=None: False)
    assert "choose an online service" in local_model.missing()
    monkeypatch.setattr(local_model, "installed", lambda model=None: True)
    monkeypatch.setattr(local_model, "nvidia_card", lambda: False)
    assert "NVIDIA graphics card" in local_model.missing()
    monkeypatch.setattr(local_model, "nvidia_card", lambda: True)
    monkeypatch.setattr(local_model, "gpu_folders", lambda: [])
    assert "not downloaded yet" in local_model.missing()
    monkeypatch.setattr(local_model, "gpu_folders", lambda: ["a folder"])
    assert local_model.missing() == ""


def test_the_real_download_is_two_gigabytes_from_secure_addresses():
    assert local_model.gb(local_model.size()) == "2.0 GB"
    assert all(len(part.sha256) == 64 and part.url.startswith("https://") for part in local_model.PARTS)
