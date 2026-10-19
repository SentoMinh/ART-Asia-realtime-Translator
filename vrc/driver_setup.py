"""Install only the driver installer pinned by the shipped app, after UI consent."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

import httpx


class DriverSetupError(Exception):
    pass


def driver_registered():
    """Check our Windows driver service, including installed but inactive devices.

    None means the registry could not be checked; it must not mean missing.
    Registration alone does not establish that the audio endpoints are usable.
    """
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SYSTEM\CurrentControlSet\Services\VrctAudio",
                            0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY):
            return True
    except FileNotFoundError:
        return False
    except (OSError, ImportError):
        return None


def installer_manifest():
    path = Path(__file__).resolve().parent.parent / "assets" / "driver-installer.json"
    if not path.exists():
        return None  # No signed installer has been published yet.
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data["url"].startswith("https://github.com/SentoMinh/vrchat-translator-public/releases/download/"):
        raise DriverSetupError("Invalid driver installer download address.")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", data["sha256"]):
        raise DriverSetupError("Invalid driver installer checksum.")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", data["signer_thumbprint"]):
        raise DriverSetupError("Invalid driver installer signing certificate.")
    if not isinstance(data["size"], int) or not 0 < data["size"] <= 256 * 1024 * 1024:
        raise DriverSetupError("Invalid driver installer size.")
    return data


def download_and_install(manifest, cancel):
    """The caller must obtain explicit download/install consent before calling this."""
    if cancel.is_set():
        return False
    with tempfile.TemporaryDirectory(prefix="vrct-driver-") as folder:
        installer = Path(folder) / "VrctAudioSetup.exe"
        digest, size = hashlib.sha256(), 0
        with httpx.stream("GET", manifest["url"], follow_redirects=True, timeout=30) as response:
            response.raise_for_status()
            with installer.open("wb") as output:
                for chunk in response.iter_bytes():
                    if cancel.is_set():
                        return False
                    size += len(chunk)
                    if size > manifest["size"]:
                        raise DriverSetupError("Driver download size does not match this release.")
                    digest.update(chunk)
                    output.write(chunk)
        if size != manifest["size"] or digest.hexdigest() != manifest["sha256"].lower():
            raise DriverSetupError("Driver download verification failed.")
        env = os.environ.copy()
        env["VRCT_DRIVER_INSTALLER"] = str(installer)
        env["VRCT_DRIVER_SIGNER"] = manifest["signer_thumbprint"]
        verify = "$s = Get-AuthenticodeSignature -LiteralPath $env:VRCT_DRIVER_INSTALLER; if ($s.Status -ne 'Valid' -or $s.SignerCertificate.Thumbprint -ne $env:VRCT_DRIVER_SIGNER) { exit 1 }"
        subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", verify],
                       env=env, check=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=60)
        if cancel.is_set():
            return False
        # The installer is interactive: show its UI and allow Windows to ask for admin consent.
        launch = "$ErrorActionPreference='Stop'; $p = Start-Process -FilePath $env:VRCT_DRIVER_INSTALLER -Verb RunAs -WindowStyle Normal -Wait -PassThru; if ($p.ExitCode -notin @(0,3010)) { exit 1 }"
        subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", launch],
                       env=env, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return True
