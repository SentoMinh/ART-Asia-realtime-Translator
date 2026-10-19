"""Keep every test away from this PC's provider credentials."""
import pytest

CUSTOM_URL = "https://custom.test/v1"


@pytest.fixture(autouse=True)
def isolated_models(tmp_path, monkeypatch):
    from engine import services
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    monkeypatch.setattr(services, "_cache", (None, {}))
