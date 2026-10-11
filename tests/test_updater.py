"""The friends' program updating itself from GitHub releases (ui/updater.py), and the two editions."""
from __future__ import annotations

import hashlib

import pytest

from ui import updater
from ui.config import Settings

LATEST = "https://api.github.com/repos/owner/friends-builds/releases/latest"   # conftest's edition
FILE = "https://github.com/owner/friends-builds/releases/download/v0.9.9/VRChat-Translator.exe"


class Answer:
    def __init__(self, status=200, body=None, data=b""):
        self.status_code, self._body, self._data = status, body or {}, data

    def json(self):
        return self._body

    def iter_bytes(self, size):
        for start in range(0, len(self._data), size):
            yield self._data[start:start + size]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Http:
    def __init__(self, release, data=b""):
        self.release, self.data, self.asked, self.headers = release, data, [], []

    def get(self, url, headers=None):
        self.asked.append(url)
        self.headers.append(headers or {})
        return Answer(body=self.release)

    def stream(self, method, url, headers=None):
        self.asked.append(url)
        self.headers.append(headers or {})
        return Answer(data=self.data)


def release(data: bytes, version="v0.9.9", digest=None, name="VRChat-Translator.exe") -> dict:
    """What GitHub says about a release with one file attached."""
    return {"tag_name": version, "assets": [
        {"name": "notes.txt", "size": 5, "browser_download_url": "https://example.test/notes.txt"},
        {"name": name, "size": len(data), "browser_download_url": FILE,
         "digest": digest or "sha256:" + hashlib.sha256(data).hexdigest()}]}


@pytest.fixture
def program(tmp_path):
    exe = tmp_path / "VRChat-Translator.exe"
    exe.write_bytes(b"version 0.9.8")
    return exe


def test_a_newer_release_is_downloaded_next_to_the_program(program):
    data = b"version 0.9.9" * 1000
    ready, http = [], Http(release(data), data)
    assert updater.Updater(program, "0.9.8", http=http, on_ready=ready.append).check() == "0.9.9"
    assert updater.beside(program, ".new").read_bytes() == data and ready == ["0.9.9"]
    assert http.asked == [LATEST, FILE]
    assert program.read_bytes() == b"version 0.9.8"          # the running program is not touched


def test_the_same_or_an_older_release_is_not_downloaded(program):
    for version in ("v0.9.8", "0.9.7"):
        http = Http(release(b"x", version=version), b"x")
        assert updater.Updater(program, "0.9.8", http=http).check() == ""
        assert http.asked == [LATEST]
    assert updater.version_tuple("0.9.10") > updater.version_tuple("0.9.9")


def test_a_release_without_a_program_file_is_skipped(program):
    http = Http(release(b"x", name="VRChat-Translator.zip"), b"x")
    assert updater.Updater(program, "0.9.8", http=http).check() == "" and http.asked == [LATEST]


def test_a_damaged_download_is_thrown_away(program):
    data = b"version 0.9.9"
    http = Http(release(data, digest="sha256:" + "0" * 64), data)
    assert updater.Updater(program, "0.9.8", http=http).check() == ""
    assert not updater.beside(program, ".new").exists() and not updater.beside(program, ".part").exists()


def test_the_public_program_never_looks_for_updates(program, public_edition):
    http = Http(release(b"x"), b"x")
    assert updater.Updater(program, "0.9.8", http=http).check() == "" and http.asked == []


def test_the_download_takes_the_program_s_place_at_the_next_start(program, monkeypatch):
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", r"C:\Temp\_MEI12345")   # this copy's unpacked files
    updater.beside(program, ".new").write_bytes(b"version 0.9.9")
    started = []
    assert updater.apply_pending(program, launch=lambda args, **kw: started.append((args, kw)))
    assert program.read_bytes() == b"version 0.9.9"
    assert updater.beside(program, ".old").read_bytes() == b"version 0.9.8"
    (args, options), = started
    assert args[0] == str(program)
    assert "_PYI_APPLICATION_HOME_DIR" not in options["env"]                # the new one unpacks itself
    assert options["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    assert not updater.apply_pending(program, launch=lambda args, **kw: started.append(args))
    assert not updater.beside(program, ".old").exists() and len(started) == 1


def test_the_source_version_has_no_program_file_to_update():
    assert updater.program_file() is None


@pytest.fixture
def private_updates(tmp_path, monkeypatch):
    """The friends' edition with the developer's update service in front of a private repository."""
    import conftest
    from engine import services
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(services, "_edition", lambda: {**conftest.EDITION, "updates": "https://updates.test"})
    return services


def test_a_private_repository_updates_through_the_developer_s_service(program, private_updates):
    data = b"version 0.9.9"
    answer = release(data)
    answer["assets"][1]["browser_download_url"] = "https://updates.test/file"
    http = Http(answer, data)
    assert updater.Updater(program, "0.9.8", http=http).check() == ""      # no Dev key: not asked
    assert http.asked == []
    private_updates.save("dev", key="the-dev-key")
    assert updater.Updater(program, "0.9.8", http=http).check() == "0.9.9"
    assert http.asked == ["https://updates.test/latest", "https://updates.test/file"]
    assert all(h.get("Authorization") == "Bearer the-dev-key" for h in http.headers)


def test_the_dev_key_never_goes_to_another_address(program, private_updates):
    private_updates.save("dev", key="the-dev-key")
    data = b"version 0.9.9"
    http = Http(release(data), data)                       # the file link points at GitHub
    assert updater.Updater(program, "0.9.8", http=http).check() == "0.9.9"
    assert "Authorization" in http.headers[0] and "Authorization" not in http.headers[1]


# ---- the two editions ----------------------------------------------------------------------

def test_the_public_edition_has_no_dev_key(public_edition):
    services = public_edition
    assert services.dev() == {} and services.update_source() == ""
    assert "dev" not in services.offered() and services.default_service() == "gemini"
    assert (Settings().hearing, Settings().translating) == ("gemini", "gemini")
    assert Settings(hearing="dev").clean().hearing == "gemini"       # a friend's settings moved over
    assert "no Dev key" in services.missing("dev")


def test_the_friends_edition_reads_its_edition_file(tmp_path, monkeypatch):
    import json
    from engine import services
    file = tmp_path / "edition.json"
    file.write_text(json.dumps({"dev": {"url": "https://d.test/v1", "translate_model": "a, b"},
                                "updates": "me/builds"}), encoding="utf-8")
    monkeypatch.undo()                                   # the real _edition, reading EDITION_FILE
    monkeypatch.setattr(services, "EDITION_FILE", file)
    services._edition.cache_clear()
    try:
        assert services.setting("dev", "url") == "https://d.test/v1" and services.update_source() == "me/builds"
        assert services.translate_models("dev") == ["a", "b"] and services.default_service() == "dev"
    finally:
        services._edition.cache_clear()
