"""Startup connectivity checks use fake providers and isolated credentials."""
import os
import threading
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx
import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from engine import services
from ui.config import Settings
from ui.service_health import ServiceHealth, TIMEOUT_MESSAGE, TIMEOUT_MS
from ui.settings_window import SettingsWindow


@pytest.fixture
def health_ui(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    yield app


def until(predicate):
    for _ in range(200):
        if predicate():
            return
        QTest.qWait(10)
    pytest.fail("Background check did not complete")


def test_start_checks_configured_providers_only(health_ui, monkeypatch):
    services.save("custom_a", url="https://a.test/v1", key="test-openai")
    services.save("custom", url="https://custom.test/v1")
    calls = []

    def probe(service, url, key):
        calls.append((service, url, key))
        return True, "reachable"

    health = ServiceHealth(probe=probe)
    health.start()
    expected = {"custom_a", "custom"}
    until(lambda: all(health.status(s)[0] == "Online" for s in expected))
    assert {call[0] for call in calls} == expected
    assert ("custom", "https://custom.test/v1", "") in calls
    assert health.status("custom_b") is None
    health.stop()


def test_slow_provider_does_not_block_other_checks_or_ui(health_ui):
    services.save("custom_a", url="https://a.test/v1", key="test-openai")
    services.save("custom", url="https://custom.test")
    release = threading.Event()

    def probe(service, url, key):
        if service == "custom_a":
            release.wait(4)
        return True, "reachable"

    health = ServiceHealth(probe=probe)
    try:
        health.start()
        until(lambda: health.status("custom")[0] == "Online")
        assert health.status("custom_a")[0] == "Checking connection…"
        release.set()
        until(lambda: health.status("custom_a")[0] == "Online")
    finally:
        release.set()
        health.stop()


def test_stale_key_results_are_ignored_and_errors_redacted(health_ui):
    services.save("custom_a", url="https://a.test/v1", key="old-test-key")
    release, finished = threading.Event(), threading.Event()

    def probe(service, url, key):
        if key == "old-test-key":
            release.wait(4)
            finished.set()
            return True, "old connection"
        raise OSError(f"Rejected {key}")

    health = ServiceHealth(probe=probe)
    try:
        health.start()
        services.save("custom_a", url="https://a.test/v1", key="new-test-key")
        assert health.status("custom_a") is None
        health.check("custom_a")
        until(lambda: health.status("custom_a")[0] == "Connection issue")
        release.set()
        until(finished.is_set)
        QTest.qWait(30)
        assert health.status("custom_a") == ("Connection issue", "Rejected ***")
        services.save("custom_a", url="", key="")
        health.check("custom_a")
        assert health.status("custom_a") is None
    finally:
        release.set()
        health.stop()


def test_stop_ignores_late_results(health_ui):
    services.save("custom", url="https://custom.test")
    release, finished = threading.Event(), threading.Event()
    entered = threading.Event()

    def probe(*args):
        entered.set()
        release.wait(4)
        finished.set()
        return True, "reachable"

    health = ServiceHealth(probe=probe)
    health.start()
    until(entered.is_set)
    health.stop()
    release.set()
    until(finished.is_set)
    QTest.qWait(30)
    assert health.status("custom")[0] == "Checking connection…"


def test_settings_shows_cached_status_and_rechecks_saved_changes(health_ui, monkeypatch):
    services.save("custom", url="https://custom.test")
    result = [True, "reachable"]
    health = ServiceHealth(probe=lambda *args: tuple(result))
    health.start()
    until(lambda: health.status("custom")[0] == "Online")
    parent = QWidget()
    parent.backend = SimpleNamespace(service_health=health)
    dialog = SettingsWindow(Settings(), parent)
    try:
        assert dialog._service_status["custom"].text() == "Online"
        assert "custom_b" not in dialog._service_status
        result[:] = [False, "timed out"]
        monkeypatch.setattr("ui.settings_window.ServiceDialog",
                            lambda *args: SimpleNamespace(exec=lambda: 1))
        dialog.set_up("custom")
        assert dialog._service_status["custom"].text() == "Checking connection…"
        until(lambda: dialog._service_status["custom"].text() == "Connection issue")
        assert dialog._service_status["custom"].toolTip() == "timed out"
    finally:
        health.stop()
        parent.deleteLater()


def test_snapshot_without_key_never_uses_newly_saved_credentials(health_ui):
    services.save("custom", url="https://new.test", key="new-domain-key")
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200)

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        assert services.check("custom", url="https://old.test", key="",
                              http=http, use_saved=False)[0]
    assert str(requests[0].url) == "https://old.test/models"
    assert "authorization" not in requests[0].headers


def test_deadline_finishes_stalled_request_and_ignores_late_success(health_ui):
    services.save("custom", url="https://custom.test")
    release, entered, finished = threading.Event(), threading.Event(), threading.Event()

    def probe(*args):
        entered.set()
        release.wait(4)
        finished.set()
        return True, "late success"

    assert TIMEOUT_MS == 30_000
    health = ServiceHealth(probe=probe, timeout_ms=80)
    try:
        health.start()
        until(entered.is_set)
        until(lambda: health.status("custom")[0] == "Connection issue")
        assert health.status("custom")[1] == TIMEOUT_MESSAGE
        release.set()
        until(finished.is_set)
        QTest.qWait(30)
        assert health.status("custom") == ("Connection issue", TIMEOUT_MESSAGE)
        assert not health._pending
    finally:
        release.set()
        health.stop()


def test_all_saved_apis_start_together_and_settings_reports_results(health_ui):
    for service in ("custom_a", "custom_b", "custom_c", "custom_d"):
        services.save(service, url=f"https://{service}.test/v1", key="test-key")
    entered = set()
    release = threading.Event()

    def probe(service, *args):
        entered.add(service)
        release.wait(4)
        return service != "custom_c", "rejected" if service == "custom_c" else "reachable"

    health = ServiceHealth(probe=probe)
    parent = QWidget()
    parent.backend = SimpleNamespace(service_health=health)
    try:
        health.start()
        dialog = SettingsWindow(Settings(), parent)
        assert all(dialog._service_status[s].text() == "Checking connection…"
                   for s in ("custom_a", "custom_b", "custom_c", "custom_d"))
        until(lambda: len(entered) == 4)
        release.set()
        until(lambda: all(health.status(s)[0] != "Checking connection…" for s in entered))
        assert all(dialog._service_status[s].text() == "Online"
                   for s in ("custom_a", "custom_b", "custom_d"))
        assert dialog._service_status["custom_c"].text() == "Connection issue"
        assert dialog._service_status["custom_c"].toolTip() == "rejected"
    finally:
        release.set()
        health.stop()
        parent.deleteLater()


def test_closing_settings_does_not_cancel_checks(health_ui):
    services.save("custom", url="https://custom.test")
    release = threading.Event()

    def probe(*args):
        release.wait(4)
        return True, "reachable"

    health = ServiceHealth(probe=probe)
    parent = QWidget()
    parent.backend = SimpleNamespace(service_health=health)
    try:
        health.start()
        dialog = SettingsWindow(Settings(), parent)
        dialog.show()
        dialog.close()
        QTest.qWait(10)
        release.set()
        until(lambda: health.status("custom")[0] == "Online")
    finally:
        release.set()
        health.stop()
        parent.deleteLater()


def test_no_requests_without_saved_providers(health_ui):
    health = ServiceHealth(probe=lambda *args: pytest.fail("Unexpected request"))
    health.start()
    assert not health._pending
    health.stop()
