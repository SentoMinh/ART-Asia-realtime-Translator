"""Looks for a newer version on GitHub before the window opens (source version only).

run_ui.bat runs this first. When GitHub's main branch is ahead of this folder, the folder is
brought up to date and the window then opens with the new version. It never gets in the way:

  - no internet, or GitHub slow: gives up after a few seconds, the current version opens
  - files here are being edited, or the folder is on a work branch: nothing is touched
  - this folder has changes GitHub doesn't have: nothing is touched

Set the environment variable VRCT_NO_UPDATE=1 to turn the check off.
One line per start goes to %LOCALAPPDATA%\\VRChat-Translator\\update.log.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRANCH = "main"
FETCH_TIMEOUT_S = 8       # longer than this and the window opens without the check
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class GitError(Exception):
    pass


def git(root: Path, *args: str, timeout: float = 15) -> str:
    """Run git in `root`. It must never stop to ask for a password: the start would hang."""
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=timeout,
                          env=dict(os.environ, GIT_TERMINAL_PROMPT="0"), creationflags=NO_WINDOW)
    if done.returncode != 0:
        lines = (done.stderr or done.stdout).strip().splitlines()
        raise GitError(lines[-1] if lines else "git failed")
    return done.stdout.strip()


def version(root: Path) -> str:
    try:
        found = re.search(r'__version__\s*=\s*"([^"]+)"', (root / "ui" / "__init__.py").read_text(encoding="utf-8"))
    except OSError:
        found = None
    return found.group(1) if found else "?"


def install(root: Path) -> str:
    """requirements.txt changed with the update: install what it lists. Returns what to tell."""
    python = root / ".venv-app" / "Scripts" / "python.exe"
    uv = shutil.which("uv") or str(root / ".tools" / "boot" / "Scripts" / "uv.exe")
    if not python.exists() or not Path(uv).exists():
        return "; new libraries are needed: uv pip install --python .venv-app\\Scripts\\python.exe -r requirements.txt"
    try:
        done = subprocess.run([uv, "pip", "install", "--python", str(python), "-r", "requirements.txt"],
                              cwd=root, capture_output=True, text=True, timeout=600, creationflags=NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return "; installing the new libraries failed"
    return "; new libraries installed" if done.returncode == 0 else "; installing the new libraries failed"


def update(root: Path = ROOT) -> str:
    """Bring `root` up to GitHub's main branch if that is safe. Returns one plain sentence."""
    if os.environ.get("VRCT_NO_UPDATE"):
        return "skipped: the check is turned off (VRCT_NO_UPDATE)"
    if shutil.which("git") is None:
        return "skipped: git is not installed"
    if not (root / ".git").exists():
        return "skipped: this folder was not downloaded with git"
    try:
        branch = git(root, "branch", "--show-current")
        if branch != BRANCH:
            return f"skipped: this folder is on the work branch '{branch}'"
        if git(root, "status", "--porcelain", "--untracked-files=no"):
            return "skipped: files in this folder are being edited"
        try:
            git(root, "fetch", "--quiet", "origin", BRANCH, timeout=FETCH_TIMEOUT_S)
        except (GitError, subprocess.TimeoutExpired):
            return "skipped: GitHub could not be reached"
        here, there = git(root, "rev-parse", "HEAD"), git(root, "rev-parse", "FETCH_HEAD")
        if here == there:
            return f"up to date ({version(root)})"
        if git(root, "merge-base", "HEAD", there) != here:
            return "skipped: this folder has changes that are not on GitHub"
        before = version(root)
        libraries = bool(git(root, "diff", "--name-only", here, there, "--", "requirements.txt"))
        git(root, "merge", "--ff-only", "--quiet", there)
        after = version(root)
        done = f"updated {before} -> {after}" if after != before else f"updated to the newest files ({after})"
        return done + (install(root) if libraries else "")
    except (GitError, subprocess.TimeoutExpired, OSError) as error:
        return f"skipped: {error}"


def log_file() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "VRChat-Translator" / "update.log"


def main() -> int:
    print("VRChat Translator: looking for a newer version on GitHub...", flush=True)   # plain ASCII: cmd.exe
    message = update()
    print(f"VRChat Translator: {message}", flush=True)
    try:
        log_file().parent.mkdir(parents=True, exist_ok=True)
        with log_file().open("a", encoding="utf-8") as f:
            f.write(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {message}\n")
    except OSError:
        pass
    if message.startswith("updated"):
        time.sleep(2)             # long enough to read before the window opens
    return 0                      # whatever happened, the window opens


if __name__ == "__main__":
    sys.exit(main())
