"""Reversible, opt-in development attachment of our APO to one capture endpoint.

No driver replacement, endpoint ACL changes or audio-policy changes. An explicit
--restart-audio option briefly restarts Windows audio for graph rebuilding.
Production distribution still requires a separately validated signed package.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import uuid
import winreg

CLSID = "{512D15B9-38AE-42C4-9747-ABB988252121}"
CAPTURE = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Capture"
FX = "{d04e05a6-594b-4fb6-a80d-01af5eed7d1d}"
CUSTOM = "{a5e509a4-f54b-47d9-994d-8bb2d4eadd5f}"
MODES = "{d3993a3f-99c2-4402-b5ec-a92a0367664b},5"
COM = r"SOFTWARE\Classes\CLSID" + "\\" + CLSID
REGISTRATION = r"SOFTWARE\Classes\AudioEngine\AudioProcessingObjects" + "\\" + CLSID
STATE = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "VRChat-Translator" / "MicrophoneMixer" / "attachment.json"
INSTALL = Path(os.environ.get("ProgramW6432", os.environ.get("ProgramFiles", r"C:\Program Files"))) / "VRChatTranslatorMicMixer"
NAMES = ("VrctMicApo.dll", "VrctApoProducer.dll")


class Registry:
    def read(self, path, name):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                data, kind = winreg.QueryValueEx(key, name)
                if kind not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ, winreg.REG_MULTI_SZ, winreg.REG_DWORD):
                    raise RuntimeError("Unexpected property type; attachment was not attempted.")
                return {"kind": kind, "data": data}
        except FileNotFoundError:
            return None

    def exists(self, path):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY):
                return True
        except FileNotFoundError:
            return False

    def write(self, path, name, value):
        if value is None:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as key:
                    winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass
        else:
            with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as key:
                winreg.SetValueEx(key, name, 0, value["kind"], value["data"])

    def delete_empty(self, path):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                children, values, _ = winreg.QueryInfoKey(key)
            if not children and not values:
                winreg.DeleteKeyEx(winreg.HKEY_LOCAL_MACHINE, path, winreg.KEY_WOW64_64KEY)
        except FileNotFoundError:
            pass


def make_plan(registry, endpoint, sid, destination, *, effect_slot="stream"):
    if effect_slot not in ("stream", "legacy"):
        raise ValueError("Unknown microphone effect slot.")
    endpoint = "{" + str(uuid.UUID(endpoint)).lower() + "}"
    base = CAPTURE + "\\" + endpoint
    effects = base + r"\FxProperties"
    if not registry.exists(effects):
        raise RuntimeError("This endpoint has no existing effects store. Automatic attachment is not supported.")
    if registry.read(base, "DeviceState") != {"kind": winreg.REG_DWORD, "data": 1}:
        raise RuntimeError("The selected microphone is not active.")
    # Do not wrap, replace or reorder any existing endpoint or stream effect.
    for number in (1, 2, 5, 7, 13, 15):
        if registry.read(effects, f"{FX},{number}") is not None:
            raise RuntimeError("This microphone already has stream/endpoint effects. Automatic attachment would risk changing them.")
    for key in (MODES, CUSTOM + ",1", CUSTOM + ",2"):
        if registry.read(effects, key) is not None:
            raise RuntimeError("The microphone has conflicting mixer properties. No settings were changed.")
    for path in (COM, REGISTRATION):
        if registry.exists(path):
            raise RuntimeError("A mixer registration already exists. Remove it using its backup first.")
    for path in (effects, base + r"\Properties"):
        disabled = registry.read(path, "{1da5d803-d492-4edd-8c23-e0c0ffee7f0e},5")
        if disabled and disabled["data"]:
            raise RuntimeError("Audio enhancements are disabled on this microphone. Setup will not override your setting.")
    token = "{" + str(uuid.uuid4()) + "}"
    changes = []

    def add(path, name, data, kind=winreg.REG_SZ):
        changes.append({"path": path, "name": name, "before": registry.read(path, name),
                        "after": {"kind": kind, "data": data}})

    add(COM, "", "VRChat Translator microphone mixer")
    add(COM + r"\InprocServer32", "", str(destination / NAMES[0]))
    add(COM + r"\InprocServer32", "ThreadingModel", "Both")
    for name, value in {"FriendlyName": "VRChat Translator microphone mixer", "Copyright": "VRChat Translator",
                        "MajorVersion": 0, "MinorVersion": 1, "Flags": 14, "MinInputConnections": 1,
                        "MaxInputConnections": 1, "MinOutputConnections": 1, "MaxOutputConnections": 1,
                        "MaxInstances": 0xffffffff, "NumAPOInterfaces": 1,
                        "APOInterface0": "{FD7F2B29-24D0-4B5C-B177-592C39F9CA10}"}.items():
        add(REGISTRATION, name, value, winreg.REG_DWORD if isinstance(value, int) else winreg.REG_SZ)
    add(effects, CUSTOM + ",1", token)
    add(effects, CUSTOM + ",2", sid)
    add(effects, MODES, ["{C18E2F7E-933D-4965-B7D1-1EEF228D2AF3}",
                        "{98951333-B9CD-48B1-A0A3-FF40682D73F7}",
                        "{FC1CFC9B-B9D6-4CFA-B5E0-4BB2166878B2}",
                        "{4780004E-7133-41D8-8C74-660DADD2C0EE}"], winreg.REG_MULTI_SZ)
    add(effects, FX + (",1" if effect_slot == "legacy" else ",5"), CLSID)
    return {"schema": 1, "endpoint": endpoint, "token": token, "sid": sid,
            "directory": str(destination), "phase": "prepared", "changes": changes,
            "effect_slot": effect_slot}


def save_state(state, path=STATE):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        json.dump(state, output, indent=2)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)


def protect_state_directory():
    """Only administrators/SYSTEM can alter the rollback journal; users can read."""
    parent = STATE.parent
    if parent.resolve() != parent.absolute():
        raise RuntimeError("The setup state directory must not be redirected.")
    parent.mkdir(parents=True, exist_ok=True)
    descriptor = ctypes.c_void_p()
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
    advapi.SetFileSecurityW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_void_p]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;FR;;;BU)", 1, ctypes.byref(descriptor), None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not advapi.SetFileSecurityW(str(parent), 0x80000004, descriptor):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.LocalFree(descriptor)


def validate_journal(state):
    endpoint = "{" + str(uuid.UUID(state["endpoint"])).lower() + "}"
    if state.get("schema") != 1 or state.get("directory") != str(INSTALL):
        raise RuntimeError("Unrecognized attachment journal.")
    effects = CAPTURE + "\\" + endpoint + r"\FxProperties"
    effect_slot = state.get("effect_slot", "stream")
    if effect_slot not in ("stream", "legacy"):
        raise RuntimeError("Unrecognized microphone effect slot.")
    allowed = {COM: {""}, COM + r"\InprocServer32": {"", "ThreadingModel"},
               REGISTRATION: {"FriendlyName", "Copyright", "MajorVersion", "MinorVersion", "Flags",
                              "MinInputConnections", "MaxInputConnections", "MinOutputConnections",
                              "MaxOutputConnections", "MaxInstances", "NumAPOInterfaces", "APOInterface0"},
               effects: {CUSTOM + ",1", CUSTOM + ",2", MODES,
                         FX + (",1" if effect_slot == "legacy" else ",5")}}
    changes = state.get("changes", [])
    if len(changes) != sum(len(names) for names in allowed.values()):
        raise RuntimeError("Incomplete attachment journal.")
    seen = set()
    for change in changes:
        pair = change["path"], change["name"]
        if (pair in seen or change["name"] not in allowed.get(change["path"], set())
                or change["before"] is not None):
            raise RuntimeError("Unexpected rollback operation in attachment journal.")
        seen.add(pair)
    return state


def apply(registry, state, save):
    state["phase"] = "installing"
    save(state)  # Persist the entire rollback journal before the first mutation.
    try:
        for change in state["changes"]:
            if registry.read(change["path"], change["name"]) != change["before"]:
                raise RuntimeError("Audio configuration changed during setup; rolling back.")
            registry.write(change["path"], change["name"], change["after"])
        state["phase"] = "installed"
        save(state)
    except Exception:
        restore(registry, state, save)
        raise


def restore(registry, state, save):
    conflicts = []
    for change in reversed(state["changes"]):
        current = registry.read(change["path"], change["name"])
        if current == change["after"]:
            registry.write(change["path"], change["name"], change["before"])
        elif current != change["before"]:
            conflicts.append(change["path"] + "\\" + change["name"])
    for path in (COM + r"\InprocServer32", COM, REGISTRATION):
        registry.delete_empty(path)
    state["phase"] = "restore_conflict" if conflicts else "removed"
    state["conflicts"] = conflicts
    save(state)
    if conflicts:
        raise RuntimeError("Some properties changed after setup and were preserved. Review the rollback journal.")


def current_sid():
    import subprocess
    # whoami supplies the SID of the caller; no credentials are read.
    import csv
    text = subprocess.check_output([str(Path(os.environ["SystemRoot"]) / "System32" / "whoami.exe"),
                                    "/user", "/fo", "csv", "/nh"], text=True, creationflags=0x08000000)
    return next(csv.reader(text.splitlines()))[1]


def load_state():
    if not STATE.is_file():
        return None
    return validate_journal(json.loads(STATE.read_text(encoding="utf-8")))


def open_capture(microphone):
    """Hold a processed capture stream open, discarding its samples."""
    import sounddevice as sd
    apis = sd.query_hostapis()
    matches = [(i, device) for i, device in enumerate(sd.query_devices())
               if device["name"] == microphone and device["max_input_channels"] > 0
               and "WASAPI" in apis[device["hostapi"]]["name"]]
    if len(matches) != 1:
        raise RuntimeError("The selected microphone cannot be matched uniquely for validation.")
    index, device = matches[0]
    return sd.InputStream(device=index, samplerate=device["default_samplerate"], channels=1,
                          dtype="float32", callback=lambda *args: None)


def validate_capture(state, microphone, seconds=4):
    """Open capture and check the real host callback; discard audio, send no music."""
    from .apo_transport import probe
    with open_capture(microphone):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            if probe(Path(state["directory"]) / NAMES[1], state["token"]) == 2:
                return True
            time.sleep(.1)
    return False


def restart_audio():
    import subprocess
    powershell = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    subprocess.run([str(powershell), "-NoProfile", "-Command",
                    "Restart-Service -Name Audiosrv -Force -ErrorAction Stop"],
                   check=True, timeout=30, creationflags=0x08000000, capture_output=True)


def activate_attachment(registry, state, microphone, *, restart=False):
    """Validate the live graph; retry an unused legacy slot if SFX is ignored."""
    apply(registry, state, save_state)
    try:
        if restart:
            restart_audio()
        valid = validate_capture(state, microphone)
        if not valid and restart and state.get("effect_slot", "stream") == "stream":
            restore(registry, state, save_state)
            legacy = make_plan(registry, state["endpoint"], state["sid"],
                               Path(state["directory"]), effect_slot="legacy")
            legacy.update(hashes=state["hashes"], microphone=microphone)
            state = legacy
            apply(registry, state, save_state)
            restart_audio()
            valid = validate_capture(state, microphone)
        if not valid:
            raise RuntimeError("Windows did not activate the microphone mixer. The attachment was rolled back; no audio security settings were changed.")
        state["phase"] = "validated"
        save_state(state)
        return state
    except Exception:
        restore(registry, state, save_state)
        if restart:
            restart_audio()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "install", "remove", "status"])
    parser.add_argument("--endpoint")
    parser.add_argument("--microphone")
    parser.add_argument("--build", type=Path)
    parser.add_argument("--development", action="store_true")
    parser.add_argument("--restart-audio", action="store_true", help="Briefly interrupt Windows audio to rebuild the graph")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = {}
    try:
        registry = Registry()
        if args.action == "status":
            result = load_state() or {"phase": "not_installed"}
        elif args.action == "remove":
            if not ctypes.windll.shell32.IsUserAnAdmin():
                raise RuntimeError("Windows administrator approval is required to remove the attachment.")
            state = load_state()
            if not state:
                raise RuntimeError("No attachment rollback journal exists.")
            restore(registry, state, save_state)
            if args.restart_audio:
                restart_audio()
            result = {"phase": state["phase"]}
        else:
            if not args.endpoint:
                raise RuntimeError("Select one capture endpoint.")
            state = make_plan(registry, args.endpoint, current_sid(), INSTALL)
            result = state
            if args.action == "install":
                if not args.development:
                    raise RuntimeError("This is a development installer. A public signed installer has not been released.")
                if not ctypes.windll.shell32.IsUserAnAdmin():
                    raise RuntimeError("Windows administrator approval is required for microphone setup.")
                if not args.microphone or not args.build:
                    raise RuntimeError("Supply the exact microphone name and native build directory.")
                previous = load_state()
                if previous and previous.get("phase") not in ("removed",):
                    raise RuntimeError("Resolve the existing attachment journal before installing again.")
                build = args.build.resolve(strict=True)
                hashes = {name: hashlib.sha256((build / name).read_bytes()).hexdigest() for name in NAMES}
                # Reject the local-namespace test DLL even if someone renamed it.
                dll = ctypes.CDLL(str(build / NAMES[0]))
                dll.VrctApoBuildKind.restype = ctypes.c_int
                if dll.VrctApoBuildKind() != 1:
                    raise RuntimeError("A standalone test DLL must never be attached to Windows.")
                if INSTALL.resolve() != INSTALL.absolute():
                    raise RuntimeError("The mixer install directory must not be redirected.")
                INSTALL.mkdir(parents=True, exist_ok=True)
                for name in NAMES:
                    target = INSTALL / name
                    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != hashes[name]:
                        raise RuntimeError("A different mixer build exists. Remove it before updating.")
                    if not target.exists():
                        shutil.copy2(build / name, target)
                    if hashlib.sha256(target.read_bytes()).hexdigest() != hashes[name]:
                        raise RuntimeError("Mixer copy verification failed.")
                state.update(hashes=hashes, microphone=args.microphone)
                protect_state_directory()
                state = activate_attachment(registry, state, args.microphone, restart=args.restart_audio)
                result = {"phase": state["phase"], "microphone": args.microphone,
                          "effect_slot": state.get("effect_slot", "stream")}
        result["ok"] = True
    except Exception as error:
        result = {"ok": False, "error": str(error)}
    if args.report:
        args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
