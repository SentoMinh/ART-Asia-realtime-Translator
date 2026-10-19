"""Application release downloads and recovery of saved API settings."""
from __future__ import annotations

import hashlib

import pytest

from ui import updater
from ui.config import Settings

LATEST = "https://api.github.com/repos/SentoMinh/ART-Asia-realtime-Translator/releases/latest"
FILE = "https://github.com/SentoMinh/ART-Asia-realtime-Translator/releases/download/v0.9.9/VRChat-Translator.exe"


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


def test_updates_never_send_provider_keys(program):
    from engine import services
    services.save("custom", url="https://custom.test/v1", key="provider-secret")
    data = b"version 0.9.9"
    http = Http(release(data), data)
    assert updater.Updater(program, "0.9.8", http=http).check() == "0.9.9"
    assert http.asked == [LATEST, FILE]
    assert all("Authorization" not in headers for headers in http.headers)


def test_one_service_list_and_default_for_everyone():
    from engine import services
    assert "dev" not in services.SERVICES
    assert services.offered() == tuple(services.SERVICES)
    assert services.update_source() == "SentoMinh/ART-Asia-realtime-Translator"
    assert (Settings().hearing, Settings().translating) == ("gemini", "gemini")


def test_legacy_selection_preserves_saved_api_settings():
    from engine import services
    services.save("dev", url="https://old.test/v1", key="saved-key", hear_model="hear", translate_model="chat")
    settings = Settings(hearing="dev", translating="dev").clean()
    assert (settings.hearing, settings.translating) == ("custom", "custom")
    assert services.saved()["custom"] == services.saved()["dev"]
    assert services.setting("custom", "key") == "saved-key"


def test_legacy_selection_keeps_existing_custom_configuration():
    from engine import services
    services.save("dev", url="https://old.test/v1", key="old-key")
    services.save("custom", url="https://current.test/v1", key="current-key", translate_model="current")
    Settings(hearing="dev", translating="dev").clean()
    assert services.saved()["custom"] == {"url": "https://current.test/v1", "key": "current-key", "translate_model": "current"}


def test_legacy_installation_defaults_and_saved_model_overrides(tmp_path, monkeypatch):
    import json
    from engine import services
    monkeypatch.setattr(services, "__file__", str(tmp_path / "engine" / "services.py"))
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "edition.json").write_text(json.dumps({"dev": {
        "url": "https://old.test/v1", "key_file": "old_key.txt",
        "hear_model": "default-hear", "translate_model": "default-chat"}}), encoding="utf-8")
    services.save("dev", translate_model="chosen-chat")
    (services.models_file().parent / "old_key.txt").write_text("saved-key", encoding="utf-8")
    Settings(hearing="dev", translating="dev").clean()
    assert services.saved()["custom"] == {
        "url": "https://old.test/v1", "key": "saved-key", "hear_model": "default-hear", "translate_model": "chosen-chat"}


def test_missing_legacy_url_does_not_switch_to_an_unconfigured_provider(tmp_path, monkeypatch):
    from engine import services
    monkeypatch.setattr(services, "__file__", str(tmp_path / "engine" / "services.py"))
    services.save("dev", key="saved-key", translate_model="chosen-chat")
    settings = Settings(hearing="dev", translating="dev").clean()
    assert settings.hearing == settings.translating == "custom"
    assert services.setting("custom", "key") == "saved-key"
    assert "has no address yet" in services.missing("custom")
