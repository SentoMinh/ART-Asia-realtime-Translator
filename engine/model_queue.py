"""Queue for downloading local hearing and translating models.

Runs up to VRCT_MODEL_DOWNLOADS (default 2, 1..4) downloads in parallel. The queue is saved to
%LOCALAPPDATA%\\VRChat-Translator\\local-model\\queue.json so interrupted or background downloads
resume when the app starts, while an explicitly stopped model stays stopped.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
from pathlib import Path
from typing import Callable

from . import local_model

log = logging.getLogger("engine.model_queue")

DEFAULT_CONCURRENCY = 2
MIN_CONCURRENCY = 1
MAX_CONCURRENCY = 4

# States
STATE_IDLE = "idle"
STATE_QUEUED = "queued"
STATE_DOWNLOADING = "downloading"
STATE_STOPPED = "stopped"
STATE_READY = "ready"
STATE_ERROR = "error"


def max_concurrent_downloads() -> int:
    try:
        val = int(os.environ.get("VRCT_MODEL_DOWNLOADS", DEFAULT_CONCURRENCY))
        return min(max(val, MIN_CONCURRENCY), MAX_CONCURRENCY)
    except (TypeError, ValueError):
        return DEFAULT_CONCURRENCY


def queue_path() -> Path:
    return local_model.folder() / "queue.json"


class ModelQueue:
    def __init__(self, root: Path | None = None, fetch_fn=local_model.download, auto_resume: bool = True):
        self._root = root
        self._fetch = fetch_fn
        self._lock = threading.Lock()
        self._queue: list[str] = []
        self._states: dict[str, str] = {}
        self._errors: dict[str, str] = {}
        self._active_workers: dict[str, tuple[threading.Thread, threading.Event]] = {}
        self._progress_listeners: list[Callable[[str, int, int], None]] = []
        self._state_listeners: list[Callable[[str, str, str], None]] = []
        self.load()
        if auto_resume:
            self.resume_saved()

    @property
    def root(self) -> Path:
        return self._root or local_model.folder()

    def _file(self) -> Path:
        return self.root / "queue.json"

    def add_progress_listener(self, fn: Callable[[str, int, int], None]) -> None:
        with self._lock:
            if fn not in self._progress_listeners:
                self._progress_listeners.append(fn)

    def remove_progress_listener(self, fn: Callable[[str, int, int], None]) -> None:
        with self._lock:
            if fn in self._progress_listeners:
                self._progress_listeners.remove(fn)

    def add_state_listener(self, fn: Callable[[str, str, str], None]) -> None:
        with self._lock:
            if fn not in self._state_listeners:
                self._state_listeners.append(fn)

    def remove_state_listener(self, fn: Callable[[str, str, str], None]) -> None:
        with self._lock:
            if fn in self._state_listeners:
                self._state_listeners.remove(fn)

    def _notify_progress(self, model: str, done: int, total: int) -> None:
        with self._lock:
            listeners = list(self._progress_listeners)
        for fn in listeners:
            try:
                fn(model, done, total)
            except Exception:
                log.exception("Error in progress listener")

    def _notify_state(self, model: str, state: str, problem: str = "") -> None:
        with self._lock:
            listeners = list(self._state_listeners)
        for fn in listeners:
            try:
                fn(model, state, problem)
            except Exception:
                log.exception("Error in state listener")

    def _is_ready(self, model: str) -> bool:
        try:
            return local_model.ready(self.root, model=model)
        except (KeyError, OSError):
            return False

    def state(self, model: str) -> str:
        with self._lock:
            if model in self._states:
                return self._states[model]
            if self._is_ready(model):
                return STATE_READY
            return STATE_IDLE

    def error(self, model: str) -> str:
        with self._lock:
            return self._errors.get(model, "")

    def is_active(self) -> bool:
        with self._lock:
            return bool(self._active_workers or self._queue)

    def active_models(self) -> list[str]:
        with self._lock:
            return list(self._active_workers.keys()) + [m for m in self._queue if m not in self._active_workers]

    def enqueue(self, model: str) -> bool:
        """Add a model to the download queue. Returns True if enqueued or already running."""
        with self._lock:
            if self._is_ready(model):
                self._states[model] = STATE_READY
                return False
            if model in self._active_workers:
                return True
            if model in self._queue:
                return True
            self._queue.append(model)
            self._states[model] = STATE_QUEUED
            self._errors.pop(model, None)
            self.save_locked()
        self._notify_state(model, STATE_QUEUED)
        self._pump()
        return True

    def enqueue_all(self, models: list[str] | None = None) -> None:
        """Enqueue all specified models (or all available runnable models) needing download."""
        candidates = models or list(local_model.MODELS.keys())
        for model in candidates:
            if not self._is_ready(model):
                if local_model.installed(model) and (model != "large-v3-turbo" or local_model.nvidia_card()):
                    self.enqueue(model)

    def stop(self, model: str) -> None:
        """Stop an in-flight or queued download."""
        stop_event = None
        with self._lock:
            if model in self._queue:
                self._queue.remove(model)
            self._states[model] = STATE_STOPPED
            self.save_locked()
            if model in self._active_workers:
                _, stop_event = self._active_workers[model]
        if stop_event is not None:
            stop_event.set()
        self._notify_state(model, STATE_STOPPED)
        self._pump()

    def check_queue_room(self) -> str:
        """Calculate total required disk space for all currently queued models against free disk."""
        with self._lock:
            models = [m for m in self._queue] + list(self._active_workers.keys())
        if not models:
            return ""
        try:
            waiting = self.root / local_model.WAITING
            waiting.mkdir(parents=True, exist_ok=True)
            need = 0
            for model in models:
                todo = [part for part in local_model.parts(model) if not local_model._has(part, self.root)]
                m_waiting = waiting if model == "large-v3-turbo" else waiting / model
                for part in todo:
                    try:
                        have = (m_waiting / part.name).stat().st_size
                    except OSError:
                        have = 0
                    need += max(part.size - have, 0) + sum(sz for _, _, sz in part.unzip)
            free = shutil.disk_usage(waiting).free
            if free < need:
                drive = waiting.drive or str(waiting)
                return f"Not enough free space on {drive}: {local_model.gb(need)} needed for queue, {local_model.gb(free)} free"
        except OSError:
            pass
        return ""

    def _pump(self) -> None:
        limit = max_concurrent_downloads()
        to_start: list[str] = []
        with self._lock:
            while len(self._active_workers) < limit and self._queue:
                next_model = self._queue.pop(0)
                if self._is_ready(next_model):
                    self._states[next_model] = STATE_READY
                    continue
                stop_event = threading.Event()
                worker = threading.Thread(
                    target=self._run_worker,
                    args=(next_model, stop_event),
                    name=f"model-dl-{next_model}",
                    daemon=True,
                )
                self._active_workers[next_model] = (worker, stop_event)
                self._states[next_model] = STATE_DOWNLOADING
                self.save_locked()
                to_start.append(next_model)

        for model in to_start:
            self._notify_state(model, STATE_DOWNLOADING)
            with self._lock:
                worker, _ = self._active_workers[model]
            worker.start()

    def _run_worker(self, model: str, stop_event: threading.Event) -> None:
        problem = ""
        state = STATE_READY
        try:
            def on_prog(done: int, total: int):
                self._notify_progress(model, done, total)

            self._fetch(
                progress=on_prog,
                stop=stop_event.is_set,
                root=self.root,
                model=model,
            )
            state = STATE_READY
        except local_model.Stopped:
            state = STATE_STOPPED
        except local_model.DownloadError as error:
            state = STATE_ERROR
            problem = str(error)
        except Exception as error:
            log.exception("Download worker failed for %s", model)
            state = STATE_ERROR
            problem = str(error) or type(error).__name__

        with self._lock:
            self._active_workers.pop(model, None)
            self._states[model] = state
            if problem:
                self._errors[model] = problem
            else:
                self._errors.pop(model, None)
            self.save_locked()

        self._notify_state(model, state, problem)
        self._pump()

    def resume_saved(self) -> None:
        """Resume any models that were downloading or queued when the app last exited."""
        with self._lock:
            to_resume: list[str] = []
            for model, st in list(self._states.items()):
                if self._is_ready(model):
                    self._states[model] = STATE_READY
                    if model in self._queue:
                        self._queue.remove(model)
                elif st in (STATE_DOWNLOADING, STATE_QUEUED):
                    if model not in self._queue and model not in self._active_workers:
                        to_resume.append(model)
                        self._states[model] = STATE_QUEUED
            for model in to_resume:
                self._queue.append(model)
            self.save_locked()
        if to_resume:
            self._pump()

    def save_locked(self) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            data = {
                "queue": self._queue,
                "states": self._states,
                "errors": self._errors,
            }
            tmp = self._file().with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp.replace(self._file())
        except OSError:
            log.exception("Could not save model queue state")

    def save(self) -> None:
        with self._lock:
            self.save_locked()

    def load(self) -> None:
        with self._lock:
            try:
                if self._file().is_file():
                    data = json.loads(self._file().read_text(encoding="utf-8"))
                    self._queue = list(data.get("queue", []))
                    self._states = dict(data.get("states", {}))
                    self._errors = dict(data.get("errors", {}))
            except (OSError, ValueError):
                log.exception("Could not load model queue state")


_shared_queue: ModelQueue | None = None


def shared(root: Path | None = None) -> ModelQueue:
    global _shared_queue
    if _shared_queue is None or (root is not None and _shared_queue.root != root):
        _shared_queue = ModelQueue(root=root)
    return _shared_queue
