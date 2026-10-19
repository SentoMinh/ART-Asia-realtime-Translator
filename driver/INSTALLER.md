# Historical virtual-driver installer design

This document describes the earlier virtual-microphone prototype, not the current music dialog. Version 0.11.5 uses the [APO mixer and bundled setup helper](../apo/README.md). The following downloader and kernel-installer design is retained for reference; it is not the release workflow for the current app.

The earlier design asks for explicit download/install consent when the music dialog finds no driver. Declining leaves normal translation usable and music routing off. There is no background driver installation.

No installer is published or configured yet. `vrc/driver_setup.py` deliberately returns unavailable when `assets/driver-installer.json` is absent. Do not add a placeholder manifest to a release.

Once the driver and installer have passed Windows 10/11 validation and signing, publish the installer as an asset in the public repository. All users use the same public, credential-free driver package. Then add a bundled `assets/driver-installer.json` with these fields:

- `url`: exact HTTPS asset URL under `https://github.com/SentoMinh/vrchat-translator-public/releases/download/`.
- `sha256`: the installer's 64-character SHA-256 digest.
- `size`: exact byte count, at most 256 MiB.
- `signer_thumbprint`: the 40-character thumbprint of its trusted Authenticode signing certificate.

The application downloads only after Yes, verifies size, hash and Authenticode signer, and starts the interactive installer with Windows elevation. It never substitutes an unsigned installer. Closing the dialog cancels an in-progress download; an installer already launched remains a separate Windows process. Restart the translator afterward to refresh cached audio devices.

The installer must install the separately Microsoft-signed kernel package, create/update exactly one `Root\VRCT_Audio` device, handle existing versions without duplicate adapters, and offer removal. Signing the setup EXE alone does not sign the kernel driver. Do not disable Secure Boot or signature enforcement.

## Native installer prototype

`setup/setup.cpp` builds as an x64 standalone EXE with a static C++ runtime. It uses SetupAPI/NewDev and has three actions:

- `--status`: read-only enumeration by exact hardware ID; includes disconnected devices and reports device-start/problem status.
- `--install` (default only when a signed payload is embedded): administrator elevation and confirmation, protected temporary extraction, package staging, create a root device only if absent, and install/update it. A global mutex serializes setup instances. Multiple existing devices are an error; newer drivers are not forcibly downgraded. A failed first installation attempts removal of only the newly created device and reports rollback failure.
- `--remove`: administrator elevation and confirmation, removes the matching device. The Windows driver-store package is retained, which is explicitly reported. It does not silently delete arbitrary OEM packages.

Restart requests return code 3010 without restarting the computer. Successful setup asks the user to restart the translator and select its microphone in VRChat. Installation/removal still needs live VM validation, including failure, cancellation and reboot scenarios.

Build a diagnostic-only executable (no payload, no device changes):

```powershell
pwsh -File driver/build-setup.ps1 -OutputDirectory .tools/audio-setup-dev
.tools/audio-setup-dev/VrctAudioSetup.exe --status
```

To produce a candidate installer after Microsoft returns a signed package:

```powershell
pwsh -File driver/build-setup.ps1 -OutputDirectory .tools/audio-setup-signed -SignedPackage C:/DriverSigning/ReturnedPackage
```

The package needs `VrctAudio.sys`, `VrctAudio.inf`, `VrctAudio.cat` and the retained `MICROSOFT-LICENSE`. The build rejects unsigned/test-signed catalogs, requires a trusted Microsoft Hardware Compatibility Publisher catalog, and runs SignTool kernel-policy verification on both SYS and INF catalog membership. Files are embedded in the EXE, so the user does not select an arbitrary INF. The resulting EXE still needs publisher Authenticode signing, Windows 10/11 validation and release publication before adding the app manifest.

## Signing handoff

Microsoft requires an EV certificate associated with the Hardware Developer account. Submission files may be signed with a registered signing certificate under Microsoft's [code-signing requirements](https://learn.microsoft.com/en-us/windows-hardware/drivers/dashboard/code-signing-reqs). Registration involves your organization/account and signing agreements; this cannot be supplied by generating a local test certificate.

Prepare an unsigned development submission CAB with the matching Release PDB:

```powershell
pwsh -File driver/prepare-submission.ps1 -DriverPackage C:/DriverBuild/package-Release -Symbols C:/DriverBuild/VrctAudio.pdb -OutputDirectory .tools/audio-submission
```

This stages SYS, INF, CAT and PDB under one `VrctAudio` CAB directory and writes source hashes. It does not sign or upload anything. Follow [Microsoft's submission process](https://learn.microsoft.com/en-us/windows-hardware/drivers/dashboard/code-signing-attestation) for signing and submission. Attestation is documented for testing; retail Windows Update publication requires the Windows Hardware Compatibility Program/HLK route. A trusted signature is not evidence that audio works. Complete the VM/HLK testing before any public rollout.
