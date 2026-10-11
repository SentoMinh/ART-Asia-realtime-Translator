"""Tests for the update check (tools/update.py), on throwaway git folders: a stand-in for
GitHub ("origin"), a developer's copy that publishes versions, and "this PC"."""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "vrct_update", Path(__file__).resolve().parent.parent / "tools" / "update.py")
update = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def run(folder: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.com",
                    "-c", "commit.gpgsign=false", *args], cwd=folder, check=True, capture_output=True)


def publish(developer: Path, number: str, requirements: str = "numpy\n") -> None:
    (developer / "ui").mkdir(exist_ok=True)
    (developer / "ui" / "__init__.py").write_text(f'__version__ = "{number}"\n', encoding="utf-8")
    (developer / "requirements.txt").write_text(requirements, encoding="utf-8")
    run(developer, "add", "-A")
    run(developer, "commit", "-q", "-m", f"version {number}")
    run(developer, "push", "-q", "origin", "main")


@pytest.fixture
def folders(tmp_path, monkeypatch):
    monkeypatch.delenv("VRCT_NO_UPDATE", raising=False)
    origin, developer, pc = tmp_path / "origin.git", tmp_path / "developer", tmp_path / "pc"
    run(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    run(tmp_path, "init", "-q", "-b", "main", str(developer))
    run(developer, "remote", "add", "origin", str(origin))
    publish(developer, "0.1.0")
    run(tmp_path, "clone", "-q", str(origin), str(pc))
    return developer, pc


def test_a_newer_version_on_github_is_installed_before_the_window_opens(folders):
    developer, pc = folders
    publish(developer, "0.2.0")
    assert update.update(pc) == "updated 0.1.0 -> 0.2.0"
    assert update.version(pc) == "0.2.0"
    assert update.update(pc) == "up to date (0.2.0)"


def test_nothing_is_touched_while_files_are_being_edited(folders):
    developer, pc = folders
    publish(developer, "0.2.0")
    (pc / "requirements.txt").write_text("numpy\nedited by hand\n", encoding="utf-8")
    assert "being edited" in update.update(pc)
    assert update.version(pc) == "0.1.0" and "edited by hand" in (pc / "requirements.txt").read_text()


def test_a_work_branch_is_left_alone(folders):
    developer, pc = folders
    publish(developer, "0.2.0")
    run(pc, "checkout", "-q", "-b", "my-fix")
    assert "work branch" in update.update(pc) and update.version(pc) == "0.1.0"


def test_changes_that_are_not_on_github_are_never_overwritten(folders):
    developer, pc = folders
    publish(developer, "0.2.0")
    (pc / "notes.txt").write_text("mine", encoding="utf-8")
    run(pc, "add", "-A")
    run(pc, "commit", "-q", "-m", "local work")
    assert "not on GitHub" in update.update(pc) and (pc / "notes.txt").exists()


def test_no_connection_opens_the_current_version(folders):
    _, pc = folders
    run(pc, "remote", "set-url", "origin", str(pc.parent / "nowhere.git"))
    assert update.update(pc) == "skipped: GitHub could not be reached"


def test_changed_requirements_are_installed_after_the_update(folders, monkeypatch):
    developer, pc = folders
    publish(developer, "0.2.0", requirements="numpy\nsoxr\n")
    monkeypatch.setattr(update, "install", lambda root: "; new libraries installed")
    assert update.update(pc) == "updated 0.1.0 -> 0.2.0; new libraries installed"


def test_the_check_can_be_turned_off_and_survives_a_plain_folder(folders, tmp_path, monkeypatch):
    developer, pc = folders
    publish(developer, "0.2.0")
    assert "not downloaded with git" in update.update(tmp_path)
    monkeypatch.setenv("VRCT_NO_UPDATE", "1")
    assert "turned off" in update.update(pc) and update.version(pc) == "0.1.0"


def test_new_files_under_the_same_version_number_are_reported_as_such(folders):
    developer, pc = folders
    (developer / "notes.txt").write_text("a fix without a new version number", encoding="utf-8")
    publish(developer, "0.1.0")
    assert update.update(pc) == "updated to the newest files (0.1.0)" and (pc / "notes.txt").exists()
