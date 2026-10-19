"""The Local Model's download (engine/local_model.py) as the window sees it: it runs on a
thread of its own and reports through signals. There is one for the whole program, so it
carries on while the settings window is closed."""
from __future__ import annotations

import logging
import threading
import time

from PySide6.QtCore import QObject, Signal

from engine import local_model

log = logging.getLogger("engine.local_model")     # written to engine.log with the engine's lines
REPORT_S = 0.2            # the window is told about progress this often at most
STOPPED = "stopped"       # the answer of `finished` when the user stopped it: nothing went wrong


class LocalDownload(QObject):
    progress = Signal(float, float)      # bytes here, bytes in all (too many for Qt's int)
    finished = Signal(str)               # "" = everything arrived, STOPPED, or what went wrong

    def __init__(self, fetch=local_model.download):
        super().__init__()
        self._fetch = fetch
        self._stop = threading.Event()
        self.active = False              # from start() until `finished` has reached the window
        self.finished.connect(self._ended)     # connected first: the window's own slots see it ended

    def start(self) -> None:
        if self.active:
            return
        self.active = True
        self._stop.clear()
        threading.Thread(target=self._run, name="local-model", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _ended(self, problem: str) -> None:
        self.active = False

    def _run(self) -> None:
        told = 0.0

        def progress(done: int, total: int) -> None:
            nonlocal told
            now = time.monotonic()
            if done >= total or now - told >= REPORT_S:
                told = now
                self.progress.emit(float(done), float(total))
        try:
            self._fetch(progress=progress, stop=self._stop.is_set)
            problem = ""
        except local_model.Stopped:
            problem = STOPPED
        except local_model.DownloadError as error:
            problem = str(error)
        except Exception as error:       # the window must get an answer whatever happens
            log.exception("the Local Model's download failed")
            problem = str(error) or type(error).__name__
        log.info("the Local Model's download ended: %s", problem or "everything arrived")
        self.finished.emit(problem)


_shared: LocalDownload | None = None


def shared() -> LocalDownload:
    global _shared
    if _shared is None:
        _shared = LocalDownload()
    return _shared
