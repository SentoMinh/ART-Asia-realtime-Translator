# VRChat Translator virtual microphone — development source

**Historical prototype, unused by the current app.** Version 0.11.5 uses the physical-microphone [APO mixer](../apo/README.md) and bundled setup described in [MUSIC_SETUP.md](../MUSIC_SETUP.md). This directory is retained for reference; its kernel driver is not included in the current exports.

This earlier design replaced the third-party cable proposal. Its intended path was:

`selected app + physical mic -> Python mixer -> VRChat Translator Mix -> WaveRT bridge -> VRChat Translator Microphone -> VRChat`

On Windows 10 22H2, app audio reaches the Python mixer through a separate **VRChat Translator Music** playback device and WASAPI loopback. The user assigns the music app to that device in Windows sound settings. Windows 11 retains per-process capture. The dedicated Music device has a separate ring and never feeds the microphone directly, so Start/Stop and music gain still apply.

**Not release-ready.** The x64 Release driver compiles with zero warnings/errors using Visual Studio Build Tools 2022, SDK/WDK 10.0.26100.0, KMDF 1.15 and the Windows 10 19041 API target. Universal API validation, InfVerif `/u`, and Inf2Cat checks passed; an unsigned catalog was generated. The driver has not been installed, Microsoft-signed, or tested on real Windows audio hardware. App tests do not establish driver correctness. Do not distribute this development package as a working microphone or bundle it in a normal release.

## Source and build

The Windows audio implementation derives from Microsoft's [SysVAD sample](https://github.com/microsoft/Windows-driver-samples/tree/2dc3fd3a0cc84a2933f2194e7ec0871584979071/audio/sysvad), under the Microsoft Public License (MS-PL) in the pinned repository. `prepare.py` requires that exact revision and an unmodified source checkout, copies it into a new build tree, retains the Microsoft license, and applies our changes. It never overwrites an existing tree or installs anything. Our bridge and INF remain reviewable in this directory instead of checking in an entire upstream repository. Retain the upstream copyright/license notices when distributing derived source or binaries.

```powershell
git clone --filter=blob:none --sparse https://github.com/microsoft/Windows-driver-samples.git .tools/windows-driver-samples
git -C .tools/windows-driver-samples checkout 2dc3fd3a0cc84a2933f2194e7ec0871584979071
git -C .tools/windows-driver-samples sparse-checkout set audio/sysvad
git -C .tools/windows-driver-samples submodule update --init wil
.venv-app/Scripts/python.exe driver/prepare.py .tools/windows-driver-samples .tools/vrct-driver-build
pwsh -File driver/build.ps1 -PreparedSource .tools/vrct-driver-build -Configuration Release
```

Install Visual Studio 2022 C++ tools (including ATL and Spectre libraries), the matching SDK/WDK, and the Visual Studio WDK integration component. For Build Tools that component is `Component.Microsoft.Windows.DriverKit.BuildTools`. See [Microsoft's build instructions](https://learn.microsoft.com/en-us/samples/microsoft/windows-driver-samples/sysvad-virtual-audio-device-driver-sample/). `build.ps1` discovers 64-bit MSBuild and defaults to SDK/WDK `10.0.26100.0`; `-WdkVersion` overrides it. It compiles, verifies the INF, and creates a fresh unsigned package directory containing SYS, INF, CAT and the Microsoft license. Inf2Cat checks the Windows 10 VB and Windows 11 CO/NI/GE target families. The build preserves the explicit INF DriverVer rather than stamping a local-time date/version. It does not sign or install. Generated source belongs under `.tools`, which is ignored by Git. The driver uses hardware ID `Root\VRCT_Audio`, service `VrctAudio`, and catalog `VrctAudio.cat`.

## Implementation

- Exposes two render endpoints (Mix and Music) and one microphone endpoint, using the sample HDMI and mic miniports internally; disables Bluetooth/USB sideband support. Removes unused sample physical-speaker posture, resource-group and jack-v3 properties that require newer Windows APIs.
- Both pins use 48 kHz stereo signed 16-bit PCM. Windows shared-mode audio converts app float samples into that format. The format tables and stream validation reject incompatible raw formats.
- Each render endpoint uses its own nonpaged, spinlock-protected 100 ms ring. Its loopback readers use that ring; the microphone reads only the Mix ring. Capture reads actual render data instead of the sample's generated sine wave. Readers have independent cursors. Underflow is silence, overflow discards old data, and stale data expires after 100 ms.
- Render Stop clears buffered audio. Audio is never written to disk; the sample registry option enabling file recording is removed.
- App capture/mixing stays in user space. It auto-selects only our named playback endpoint and rejects our microphone as the voice source to prevent feedback. Endpoint naming is discovery, not authentication.

## Remaining work before a working release

1. Verify endpoint names/format negotiation and binary loading in disposable Windows 10 22H2 and Windows 11 test VMs. Compilation, Universal API validation, INF verification and catalog generation have passed. The INF targets x64 build 19045 or later and the build sets `_NT_TARGET_VERSION=0xA000008`, producing `NTDDI_VERSION=0x0A000008` (Windows 10 19041). The newer imported APIs checked, [ExAllocatePool2](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdm/nf-wdm-exallocatepool2) and [IoOpenDriverRegistryKey](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdm/nf-wdm-ioopendriverregistrykey), have documented minimums of Windows 10 2004 and 1803 respectively. These checks are not proof of runtime compatibility.
2. Validate real render-to-capture sample fidelity, underflow/overflow, mute/volume handling, latency, concurrent readers, stop/restart, app crashes, sleep/wake, and removal while streaming. Run Driver Verifier and relevant HLK tests. The shared bridge currently assumes one installed adapter; enforce one instance in the installer or move storage into each adapter before supporting multiple instances.
3. Validate the native installer prototype in clean VMs with a Microsoft-signed package. `setup/setup.cpp` now implements root-device creation, update without forced downgrade, duplicate detection, rollback attempts and device removal; `--status` is read-only. The diagnostic build cannot install/remove anything. The signed-payload build is blocked until the Microsoft-signed package is available. See [INSTALLER.md](INSTALLER.md).
4. Obtain the appropriate [Microsoft driver signature](https://learn.microsoft.com/en-us/windows-hardware/drivers/dashboard/code-signing-attestation), then bundle only the verified package. Test-signed developer binaries are not public binaries. Never change users' Secure Boot or signature enforcement to make installation succeed.
5. Validate installation and music in VRChat on clean supported Windows machines, then build the application package. Users approve driver installation and select our microphone inside VRChat once.

## Host buffer tests

`tests/bridge_test.cpp` compiles the actual `bridge.cpp` against a small user-space kernel API shim. It checks sample fidelity, independent readers, wraparound, overflow, silence on underflow, stop clearing, stale expiry, partial-frame handling, and isolation of the Music ring from the microphone Mix ring. This does not validate real spinlocks/IRQL, WaveRT, INF installation, or kernel behavior.

With a C++17 compiler, compile both sources with `driver/tests` as an include directory and run the executable. For example, from the repository root:

```powershell
clang++ -std=c++17 -Wall -Wextra -Werror -Idriver/tests driver/bridge.cpp driver/tests/bridge_test.cpp -o .tools/bridge-test.exe
.tools/bridge-test.exe
```

## Windows audio validation

`validate_audio.py` checks for exactly one stereo WASAPI Mix, Music and Microphone endpoint. Its default mode opens no streams. Missing or duplicate endpoints fail without falling back to speakers or a physical microphone:

```powershell
.venv-app/Scripts/python.exe driver/validate_audio.py --report .tools/audio-endpoints.json
```

In an isolated Windows VM **with voice chat and the translator closed**, explicitly add `--run` to stream a deterministic low-level stereo test signal. It checks two start/stop cycles for waveform fidelity and trailing silence, and verifies that Music alone does not reach the microphone. It writes a JSON report; callback underflow/overflow fails the check. Restore device volumes to unity and disable audio enhancements for the sample-fidelity measurement. A passing result does not replace latency, sleep/wake, concurrent-client, uninstall-while-streaming or HLK/Driver Verifier coverage.

The analysis tests detect silence, channel swaps, dropped samples and stale audio. Those synthetic tests passed; live audio testing has not yet run because the driver is not installed. Both Debug and Release driver builds passed compiler/INF/catalog checks, and the native diagnostic installer passed compilation, read-only status and no-payload mutation guards.
