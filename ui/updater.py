"""Download application releases from GitHub and apply them on the next start.

Source checkouts update through tools/update.py instead. Provider credentials are never
used to check for or download application updates.

Mirrors: VRCT_UPDATE_API holds one or more extra release addresses separated by commas or
semicolons; `{source}` in them is replaced by the repository. They are asked after GitHub,
for networks where GitHub cannot be reached (mainland China without a VPN). A mirror must
answer with the same JSON as GitHub's /releases/latest and name its own download link there.
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

DEFAULT_LATEST = "https://api.github.com/repos/{source}/releases/latest"
MIRROR_ENV = "VRCT_UPDATE_API"                # e.g. https://mirror.example/latest


def release_urls(source: str) -> list[str]:
    """Where the release is asked for: GitHub first, then the mirrors set on this PC."""
    urls = [DEFAULT_LATEST.format(source=source)]
    for piece in re.split(r"[,;\s]+", os.environ.get(MIRROR_ENV, "")):
        url = piece.strip().replace("{source}", source)
        if url and url not in urls:
            urls.append(url)
    return urls


def program_file() -> Path | None:
    """The running .exe; None when started from source."""
    return Path(sys.executable) if getattr(sys, "frozen", False) else None


def version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", text)[:4])


def beside(program: Path, suffix: str) -> Path:
    return program.with_name(program.name + suffix)


def leftovers(program: Path) -> list[Path]:
    """The copies an update left behind: .old, and .old2/.old3 when that name was taken."""
    return sorted(program.parent.glob(program.name + ".old*"))


def clear_leftovers(program: Path) -> None:
    """Delete the copies an update left behind. One can still be held open by a copy of the
    program that is closing; that one waits for the next start."""
    for old in leftovers(program):
        try:
            old.unlink()
        except OSError:
            log.info("the old copy %s is still in use; it is removed next time", old.name)


def free_backup(program: Path) -> Path:
    """Where the running program is renamed to: .old, or .old2 and up when a copy of the
    program that is still running holds the plain name."""
    backup = beside(program, ".old")
    for number in range(2, 100):
        if not backup.exists():
            break
        backup = beside(program, f".old{number}")
    return backup


def remove(path: Path) -> None:
    """Throw a half-written file away; a locked one waits for the next start."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        log.info("%s cannot be removed yet", path.name)


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
    clear_leftovers(program)               # left behind by the last update
    new = beside(program, ".new")
    if not new.exists():
        return False
    backup = free_backup(program)          # .old unless another copy still holds that name
    try:
        program.rename(backup)             # Windows lets a running program be renamed, not replaced
        try:
            new.rename(program)
        except OSError:
            backup.rename(program)         # put it back as it was
            raise
    except OSError:
        log.exception("the update could not be put in place")
        return False
    try:
        launch([str(program), *sys.argv[1:]], close_fds=True, env=fresh_environment())
    except OSError:
        log.exception("the updated program could not be started; restoring the previous version")
        program.rename(new)
        backup.rename(program)
        return False
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

    def release(self, http, headers: dict, source: str) -> dict | None:
        """The newest release GitHub (or a mirror named in VRCT_UPDATE_API) describes."""
        urls = release_urls(source)
        for number, url in enumerate(urls):
            try:
                answer = http.get(url, headers=headers)
            except Exception as error:                  # no route, TLS refused, timeout
                log.warning("no answer from %s: %s", url, error)
                continue
            if answer.status_code != 200:
                log.warning("%s answered %s", url, answer.status_code)
                continue
            try:
                release = answer.json()
            except ValueError:
                log.warning("%s did not answer with a release", url)
                continue
            if isinstance(release, dict):
                if number:
                    log.info("the newer version was found on the mirror %s", url)
                return release
            log.warning("%s did not answer with a release", url)
        return None

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
        release = self.release(http, headers, source)
        if release is None:
            log.info("no update server answered; the current version %s stays", self.current)
            return ""
        version = str(release.get("tag_name") or "").lstrip("vV")
        if not version:
            log.warning("the release answer has no version number")
            return ""
        asset = next((a for a in release.get("assets") or []
                      if str(a.get("name", "")).lower().startswith("vrchat-translator")
                      and str(a.get("name", "")).lower().endswith(".exe")), None)
        if version_tuple(version) <= version_tuple(self.current):
            log.info("version %s is the newest (%s is running)", version, self.current)
            return ""
        if asset is None:
            log.warning("the %s release has no program file attached to download", version)
            return ""
        size = int(asset.get("size") or 0)
        expected = str(asset.get("digest") or "").lower().removeprefix("sha256:")
        new = beside(self.program, ".new")
        if new.exists() and new.stat().st_size == size and expected:
            with new.open("rb") as cached:
                valid = hashlib.file_digest(cached, "sha256").hexdigest() == expected
            if valid:
                self._on_ready(version)
                return version
        remove(new)                             # A stale or damaged pending file must not be applied.
        part = beside(self.program, ".part")
        digest, received = hashlib.sha256(), 0
        link = str(asset["browser_download_url"])
        if not expected:
            log.warning("the %s release carries no digest; only the size is checked", version)
        remove(part)
        try:
            with http.stream("GET", link, headers=headers) as stream:
                if stream.status_code != 200:
                    log.warning("the update file could not be downloaded (%s): %s", stream.status_code, link)
                    return ""
                with open(part, "wb") as out:
                    for chunk in stream.iter_bytes(1 << 20):
                        out.write(chunk)
                        digest.update(chunk)
                        received += len(chunk)
        except Exception:
            remove(part)                        # half a download is of no use; the next start begins again
            raise
        if (size and received != size) or (expected and digest.hexdigest() != expected):
            log.warning("the downloaded update was damaged (%d of %d bytes); it is thrown away", received, size)
            remove(part)
            return ""
        part.replace(new)
        log.info("version %s downloaded; it starts next time", version)
        self._on_ready(version)
        return version
