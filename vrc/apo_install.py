"""Launch the local microphone setup with Windows UAC, after UI consent."""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import winreg

from . import apo_setup
from .apo_player import attachment_for


def native_build():
    root = Path(__file__).resolve().parents[1]
    bundled = root / "assets" / "apo"
    candidates = [bundled]
    if not getattr(sys, "frozen", False):
        candidates += sorted((root / ".tools").glob("apo-prototype*"),
                             key=lambda path: path.stat().st_mtime, reverse=True)
    return next((path for path in candidates if all((path / name).is_file() for name in apo_setup.NAMES)), None)


def setup_command(microphone):
    if getattr(sys, "frozen", False):
        return sys.executable, ["--mixer-setup", "--microphone", microphone]
    python = Path(sys.executable).with_name("python.exe")
    return str(python), ["-m", "vrc.apo_install", "--microphone", microphone]


def endpoint_for(microphone):
    """Resolve exactly one active Windows endpoint; never guess a microphone."""
    matches = []
    registry = apo_setup.Registry()
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, apo_setup.CAPTURE, 0,
                        winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
        for index in range(winreg.QueryInfoKey(key)[0]):
            endpoint = winreg.EnumKey(key, index)
            base = apo_setup.CAPTURE + "\\" + endpoint
            if registry.read(base, "DeviceState") != {"kind": winreg.REG_DWORD, "data": 1}:
                continue
            props = base + r"\Properties"
            def value(name):
                item = registry.read(props, name)
                return item["data"] if item else ""
            friendly = value("{a45c254e-df1c-4efd-8020-67d146a850e0},14")
            device = value("{a45c254e-df1c-4efd-8020-67d146a850e0},2")
            interface = value("{b3f8fa53-0004-438e-9003-51a46e139bfc},6")
            if microphone and microphone in (friendly, f"{device} ({interface})"):
                matches.append(endpoint)
    if len(matches) != 1:
        raise RuntimeError("Choose a microphone that can be matched uniquely before installing the mixer.")
    return matches[0]


def installed(microphone):
    state = attachment_for(microphone)
    if not state:
        return False
    registry = apo_setup.Registry()
    if any(registry.read(change["path"], change["name"]) != change["after"] for change in state["changes"]):
        raise RuntimeError("The installed mixer configuration changed. Review setup before reinstalling.")
    return True


def install(microphone):
    if installed(microphone):
        return {"ok": True, "already_installed": True}
    build = native_build()
    if build is None:
        raise RuntimeError("The microphone mixer files are missing from this installation.")
    endpoint = endpoint_for(microphone)
    # Perform read-only compatibility checks before requesting elevation.
    sid = apo_setup.current_sid()
    apo_setup.make_plan(apo_setup.Registry(), endpoint, sid, apo_setup.INSTALL)
    python, arguments = setup_command(microphone)
    with tempfile.TemporaryDirectory(prefix="vrct-mixer-setup-") as directory:
        report = Path(directory) / "result.json"
        arguments += ["--elevated", "--endpoint", endpoint, "--build", str(build),
                      "--user-sid", sid, "--report", str(report)]
        env = os.environ.copy()
        if getattr(sys, "frozen", False):
            env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        env.update(VRCT_SETUP_PYTHON=python, VRCT_SETUP_ARGS=subprocess.list2cmdline(arguments),
                   VRCT_SETUP_ROOT=str(Path(__file__).resolve().parents[1]))
        powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        script = ("$ErrorActionPreference='Stop'; try { "
                  "$p = Start-Process -FilePath $env:VRCT_SETUP_PYTHON -ArgumentList $env:VRCT_SETUP_ARGS "
                  "-WorkingDirectory $env:VRCT_SETUP_ROOT -Verb RunAs -WindowStyle Normal -Wait -PassThru; "
                  "exit $p.ExitCode } catch { Write-Output $_.Exception.Message; exit 1 }")
        result = subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-Command", script],
                                env=env, capture_output=True, text=True, creationflags=0x08000000)
        if not report.is_file():
            raise RuntimeError("Setup did not run. Administrator approval may have been cancelled. " + result.stdout.strip())
        outcome = json.loads(report.read_text(encoding="utf-8"))
        if result.returncode or not outcome.get("ok"):
            raise RuntimeError(outcome.get("error", "Microphone setup failed."))
        if not installed(microphone):
            raise RuntimeError("Setup finished without a validated microphone attachment.")
        return {"ok": True, "already_installed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microphone", required=True)
    parser.add_argument("--elevated", action="store_true")
    parser.add_argument("--endpoint")
    parser.add_argument("--build")
    parser.add_argument("--user-sid")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        if args.elevated:
            if not args.report or not args.build or not args.endpoint:
                raise RuntimeError("Missing setup arguments.")
            if apo_setup.current_sid() != args.user_sid:
                raise RuntimeError("Run setup using administrator approval for the same Windows account.")
            if endpoint_for(args.microphone) != args.endpoint:
                raise RuntimeError("The selected microphone changed before setup started.")
            if getattr(sys, "frozen", False):
                # Use the elevated executable's own bundled files.
                build = native_build()
                if build is None:
                    raise RuntimeError("The bundled microphone mixer files are missing.")
                args.build = str(build)
                if ctypes.windll.kernel32.AllocConsole():
                    sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
                    sys.stderr = sys.stdout
            print("Installing the microphone mixer. Windows audio will briefly restart.", flush=True)
            sys.argv = [sys.argv[0], "install", "--development", "--restart-audio",
                        "--microphone", args.microphone, "--endpoint", args.endpoint,
                        "--build", args.build, "--report", str(args.report)]
            return apo_setup.main()
        outcome = install(args.microphone)
    except Exception as error:
        outcome = {"ok": False, "error": str(error)}
    if args.report:
        args.report.write_text(json.dumps(outcome), encoding="utf-8")
    print(json.dumps(outcome), flush=True)
    return 0 if outcome["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
