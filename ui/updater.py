"""Updates for the program file (VRChat-Translator.exe) that friends are given.

At every start the friends' program asks where its edition file says (engine/services.py →
update_source()) for the newest release: the developer's own update service, which reads the
private GitHub repository and answers only to a known Dev key, or a public GitHub repository
("owner/name"). When that release is newer and has an .exe attached, the file is downloaded
next to the program in the background (<name>.exe.part, then .new once its size and SHA-256 are
right) and takes the old one's place the next time the program starts.

The source version updates through git instead (tools/update.py), and the public program has
no edition file, so for both this does nothing.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

log = logging.getLogger("engine.update")      # written to engine.log with the engine's lines


def program_file() -> Path | None:
    """The running .exe; None when started from source."""
    return Path(sys.executable) if getattr(sys, "frozen", False) else None


def version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", text)[:4])


def beside(program: Path, suffix: str) -> Path:
    return program.with_name(program.name + suffix)


def fresh_environment() -> dict:
    """The one-file program unpacks itself into a temporary folder and tells its own child
    processes where through environment variables. The new version must unpack itself again
    (that folder is deleted when this copy ends), so those variables are left out."""
    env = {name: value for name, value in os.environ.items()
           if not (name.startswith("_PYI") or name.startswith("_MEIPASS"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def apply_pending(program: Path, launch=subprocess.Popen) -> bool:
    """At start, before the window: a finished download takes the program's place and is
    started. True = this copy should end now, the new version is starting."""
    old, new = beside(program, ".old"), beside(program, ".new")
    try:
        old.unlink(missing_ok=True)            # left behind by the last update
    except OSError:
        pass                                   # still closing: removed next time
    if not new.exists() or old.exists():
        return False
    try:
        program.rename(old)                    # Windows lets a running program be renamed, not replaced
        try:
            new.rename(program)
        except OSError:
            old.rename(program)                # put it back as it was
            raise
    except OSError:
        log.exception("the update could not be put in place")
        return False
    launch([str(program), *sys.argv[1:]], close_fds=True, env=fresh_environment())
    return True


class Updater:
    """Looks once for a newer version and downloads it, on a thread of its own.
    `on_ready(version)` is called (from that thread) when it is ready for the next start."""

    def __init__(self, program: Path, current: str, http=None, on_ready=lambda version: None):
        self.program = program
        self.current = current
        self._http = http
        self._on_ready = on_ready

    def start(self) -> None:
        threading.Thread(target=self._run, name="update", daemon=True).start()

    def _run(self) -> None:
        try:
            self.check()
        except Exception:
            log.exception("looking for an update failed")

    def check(self) -> str:
        """The newer version now waiting for the next start, or "" when there is none."""
        from engine import services
        source = services.update_source()
        if not source:
            return ""
        http = self._http
        if http is None:
            import httpx
            http = httpx.Client(timeout=httpx.Timeout(20, read=60), follow_redirects=True)
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "VRChat-Translator"}
        if source.startswith("https://"):
            # the developer's update service: it lets in programs that hold a Dev key it knows
            key = services.setting("dev", "key")
            if not key:
                return ""
            latest, mine = f"{source.rstrip('/')}/latest", {**headers, "Authorization": f"Bearer {key}"}
        else:
            latest, mine = f"https://api.github.com/repos/{source}/releases/latest", headers
        answer = http.get(latest, headers=mine)
        if answer.status_code != 200:
            return ""
        release = answer.json()
        version = str(release.get("tag_name") or "").lstrip("vV")
        asset = next((a for a in release.get("assets") or []
                      if str(a.get("name", "")).lower().endswith(".exe")), None)
        if not version or asset is None or version_tuple(version) <= version_tuple(self.current):
            return ""
        size = int(asset.get("size") or 0)
        expected = str(asset.get("digest") or "").lower().removeprefix("sha256:")
        new = beside(self.program, ".new")
        if new.exists() and new.stat().st_size == size:
            self._on_ready(version)             # downloaded before, not started yet
            return version
        part = beside(self.program, ".part")
        digest, received = hashlib.sha256(), 0
        link = str(asset["browser_download_url"])
        # the Dev key goes only to the service that asked for it, never to another address
        with http.stream("GET", link, headers=mine if link.startswith(source) else headers) as stream:
            if stream.status_code != 200:
                return ""
            with open(part, "wb") as out:
                for chunk in stream.iter_bytes(1 << 20):
                    out.write(chunk)
                    digest.update(chunk)
                    received += len(chunk)
        if (size and received != size) or (expected and digest.hexdigest() != expected):
            log.warning("the downloaded update was damaged (%d of %d bytes); it is thrown away", received, size)
            part.unlink(missing_ok=True)
            return ""
        part.replace(new)
        log.info("version %s downloaded; it starts next time", version)
        self._on_ready(version)
        return version
