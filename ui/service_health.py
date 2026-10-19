"""Background startup checks for configured online translation providers."""
from __future__ import annotations

import hashlib
import threading
import time

from PySide6.QtCore import QObject, QTimer, Qt, Signal, Slot

from engine import services

TIMEOUT_MS = 30_000
TIMEOUT_MESSAGE = "Connection timed out after 30 seconds."

def _credentials(service):
    url, key = services.setting(service, "url"), services.setting(service, "key")
    fingerprint = hashlib.sha256((url + "\0" + key).encode()).hexdigest()
    return url, key, fingerprint


def _probe(service, url, key):
    import httpx
    with httpx.Client(timeout=TIMEOUT_MS / 1000) as http:
        # GET only: no speech uploads or translation requests.
        return services.check(service, url=url, key=key, http=http, use_saved=False)


class ServiceHealth(QObject):
    changed = Signal(str)
    _completed = Signal(str, int, str, bool, str)

    def __init__(self, parent=None, probe=_probe, timeout_ms=TIMEOUT_MS):
        super().__init__(parent)
        self._probe = probe
        self._results = {}
        self._generation = {}
        self._stopped = threading.Event()
        self._timeout_ms = timeout_ms
        self._pending = {}
        self._completed.connect(self._finish)

    def status(self, service):
        record = self._results.get(service)
        if not record or record[0] != _credentials(service)[2]:
            return None
        return record[1:]  # status text, detail; credentials are never exposed

    def start(self):
        for service in services.offered():
            self.check(service)

    def check(self, service):
        if self._stopped.is_set() or service not in services.offered():
            return
        generation = self._generation.get(service, 0) + 1
        self._generation[service] = generation
        self._clear_pending(service)
        if not services.ready(service):
            self._results.pop(service, None)
            self.changed.emit(service)
            return
        url, key, fingerprint = _credentials(service)
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setTimerType(Qt.PreciseTimer)
        timer.timeout.connect(lambda: self._expire(service, generation, fingerprint))
        self._pending[service] = (timer, time.monotonic() + self._timeout_ms / 1000)
        timer.start(self._timeout_ms)
        self._results[service] = (fingerprint, "Checking connection…", "")
        self.changed.emit(service)
        probe, stopped, completed = self._probe, self._stopped, self._completed

        def work():
            if stopped.is_set():
                return
            try:
                ok, detail = probe(service, url, key)
            except Exception as error:
                ok, detail = False, str(error) or type(error).__name__
            if key:
                detail = detail.replace(key, "***")
            if stopped.is_set():
                return
            try:
                completed.emit(service, generation, fingerprint, bool(ok), detail)
            except RuntimeError:
                pass  # the application or receiver has already closed

        threading.Thread(target=work, name=f"check-{service}", daemon=True).start()

    @Slot(str, int, str, bool, str)
    def _finish(self, service, generation, fingerprint, ok, detail):
        if (self._stopped.is_set() or self._generation.get(service) != generation
                or _credentials(service)[2] != fingerprint or service not in self._pending):
            return
        if time.monotonic() >= self._pending[service][1]:
            ok, detail = False, TIMEOUT_MESSAGE
        self._clear_pending(service)
        self._results[service] = (fingerprint, "Online" if ok else "Connection issue", detail)
        self.changed.emit(service)

    def _clear_pending(self, service):
        pending = self._pending.pop(service, None)
        if pending:
            pending[0].stop()
            pending[0].deleteLater()

    def _expire(self, service, generation, fingerprint):
        self._finish(service, generation, fingerprint, False, TIMEOUT_MESSAGE)
        if self._generation.get(service) == generation:
            self._clear_pending(service)

    def stop(self):
        self._stopped.set()
        for service in tuple(self._pending):
            self._clear_pending(service)
