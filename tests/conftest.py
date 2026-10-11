"""Shared by all tests: they run as the friends' edition (a pretend Dev key service and update
repository), in the developer's copy and in the public one alike. Tests of the public edition
switch it off."""
import pytest

DEV = "https://dev.test/v1"
EDITION = {"edition": "friends",
           "dev": {"url": DEV, "hear_model": "whisper-large-v3-turbo", "translate_model": "model-a, model-b"},
           "updates": "owner/friends-builds"}


@pytest.fixture(autouse=True)
def friends_edition(monkeypatch):
    from engine import services
    monkeypatch.setattr(services, "_edition", lambda: EDITION)


@pytest.fixture
def public_edition(monkeypatch):
    """No edition file: the program as the public download has it."""
    from engine import services
    monkeypatch.setattr(services, "_edition", lambda: {})
    return services
