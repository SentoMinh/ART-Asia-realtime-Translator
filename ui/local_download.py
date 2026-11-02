"""The Local Model's download (engine/local_model.py, engine/model_queue.py) as the window sees it:
it runs on background threads and reports through signals. There is one shared download queue for
the whole program, so downloads carry on while the settings window is closed.
"""
from __future__ import annotations

import logging
import threading
import time

from PySide6.QtCore import QObject, Signal

from engine import local_model, model_queue
from engine.model_queue import (
    STATE_DOWNLOADING,
    STATE_ERROR,
    STATE_IDLE,
    STATE_QUEUED,
    STATE_READY,
    STATE_STOPPED,
)

log = logging.getLogger("engine.local_model")     # written to engine.log with the engine's lines
REPORT_S = 0.2            # the window is told about progress this often at most
STOPPED = "stopped"       # the answer of `finished` when the user stopped it: nothing went wrong


class LocalDownload(QObject):
    # Per-model signals
    progress = Signal(str, float, float)   # model, bytes arrived, bytes in total
    state = Signal(str, str, str)          # model, state, problem (if any)
    # Compatibility signal for main window and existing tests
    finished = Signal(str)                 # "" = everything arrived, STOPPED, or what went wrong

    def __init__(self, fetch=local_model.download, queue: model_queue.ModelQueue | None = None):
        super().__init__()
        self._fetch = fetch
        self._queue = queue or model_queue.ModelQueue(fetch_fn=fetch, auto_resume=True)
        self._stop = threading.Event()
        self.model = local_model.selected()
        self._manual_active = False
        self._told_times: dict[str, float] = {}

        self._queue.add_progress_listener(self._on_queue_progress)
        self._queue.add_state_listener(self._on_queue_state)

    @property
    def queue(self) -> model_queue.ModelQueue:
        return self._queue

    @property
    def active(self) -> bool:
        return self._manual_active or self._queue.is_active()

    @active.setter
    def active(self, value: bool) -> None:
        self._manual_active = value

    def is_model_active(self, model: str) -> bool:
        st = self._queue.state(model)
        return st in (STATE_DOWNLOADING, STATE_QUEUED)

    def start(self, model: str | None = None) -> None:
        self.model = model or local_model.selected()
        self._stop.clear()
        self._queue.enqueue(self.model)

    def start_all(self, models: list[str] | None = None) -> None:
        self._queue.enqueue_all(models)

    def stop(self, model: str | None = None) -> None:
        target = model or self.model
        self._stop.set()
        self._queue.stop(target)

    def get_state(self, model: str) -> str:
        return self._queue.state(model)

    def get_error(self, model: str) -> str:
        return self._queue.error(model)

    def check_queue_room(self) -> str:
        return self._queue.check_queue_room()

    def _on_queue_progress(self, model: str, done: int, total: int) -> None:
        now = time.monotonic()
        told = self._told_times.get(model, 0.0)
        if done >= total or now - told >= REPORT_S:
            self._told_times[model] = now
            self.progress.emit(model, float(done), float(total))

    def _on_queue_state(self, model: str, state: str, problem: str) -> None:
        self.model = model
        self.state.emit(model, state, problem)
        if state in (STATE_READY, STATE_STOPPED, STATE_ERROR):
            reason = problem if state == STATE_ERROR else (STOPPED if state == STATE_STOPPED else "")
            self.finished.emit(reason)

    def _run(self) -> None:
        """Manual test runner path to maintain compatibility with existing tests."""
        told = 0.0

        def progress(done: int, total: int) -> None:
            nonlocal told
            now = time.monotonic()
            if done >= total or now - told >= REPORT_S:
                told = now
                self.progress.emit(self.model, float(done), float(total))

        try:
            self._fetch(progress=progress, stop=self._stop.is_set, model=self.model)
            problem = ""
        except local_model.Stopped:
            problem = STOPPED
        except local_model.DownloadError as error:
            problem = str(error)
        except Exception as error:
            log.exception("the Local Model's download failed")
            problem = str(error) or type(error).__name__

        self._manual_active = False
        log.info("the Local Model's download ended: %s", problem or "everything arrived")
        self.finished.emit(problem)


_shared: LocalDownload | None = None


def shared() -> LocalDownload:
    global _shared
    if _shared is None:
        _shared = LocalDownload(queue=model_queue.shared())
    return _shared
