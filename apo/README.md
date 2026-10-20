# Microphone APO: development mixer and bundled setup

This is the alternative to creating a new virtual microphone: a user-mode Windows Audio Processing Object mixes app music into the existing microphone capture stream. The earlier kernel driver remains in `driver/` for reference; the APO does not use its SYS file or endpoints.

**Working development installation on this PC.** The production DLL is now attached to Virtual Desktop Audio using its legacy capture-effect slot. HyperX QuadCast was previously validated, but VRChat used the headset instead. Live tests measured WAV playback and selected-app audio in headset microphone capture, then verified the tone stopped. The current source and 0.11.10 EXE support both effect slots. Fresh-machine setup, remote VRChat reception, signed public deployment and live Windows 10 validation remain outstanding; never attach the test DLL to Windows.

## Build and inspect

Requires Visual Studio 2022 C++/ATL and Windows SDK 10.0.26100.0:

```powershell
pwsh -File apo/build.ps1 -OutputDirectory .tools/apo-prototype
.venv-app/Scripts/python.exe apo/inspect_endpoints.py --report .tools/apo-endpoints.json
.venv-app/Scripts/python.exe apo/test_python_playback.py .tools/apo-prototype
```

Build outputs:

- `VrctMicApo.dll`: native COM APO, Windows 10 API baseline; no registration exports or automatic installation.
- `VrctApoProducer.dll`: app-side transport. `vrc/apo_transport.py` is its development Python binding. Open, write and close on one worker thread.
- `VrctMicApo-Test.dll`: test-only local-session transport; never distribute/register this DLL.
- `ApoTests.exe`: loads the test APO directly without COM registration, creates test media connections and verifies mixing. Also starts a hidden producer child process and verifies music transfer and stale expiry after abrupt exit.

The endpoint inspector reads only existing Capture registry records and effect-property names, including composite slots and indirectly referenced effect components. Both tested microphones reference **Microsoft Voice Clarity**, which remains unchanged. Virtual Desktop uses the previously unused legacy capture-effect slot; HyperX used the stream-effect slot. Only one microphone attachment is managed at a time.

## Audio sender

`vrc/apo_music.py` provides worker functions for PCM16 mono/stereo WAV playback and process-specific app capture. WAV data is streamed and resampled to 48 kHz stereo; producer calls stay on the worker thread and close on stop/error. Process capture reuses the existing capture package and bounded queue, refuses whole-system fallback, and does not record/re-add voice. WAV playback remains a development validation path, not a music-dialog option. The app-source UI currently requires Windows 11; Windows 10 live validation remains outstanding.

`test_python_playback.py` creates a temporary WAV fixture and starts the standalone COM test host. That host launches Python playback with the real producer DLL and verifies that audio reaches the native mixer. It also runs the native crash/stop/RAW/discovery tests. No audio endpoint is opened or modified.

After a separately validated attachment exists, the development command is:

```powershell
.venv-app/Scripts/python.exe -m vrc.apo_music --library <absolute-producer-dll-path> --token <installed-endpoint-token> --wav <pcm16-wave-file>
# Or --pid <music-app-process-id> on supported Windows versions.
```

Do not invent a token to make the command connect: only a configured, running APO host can create its corresponding transport. `vrc/apo_player.py` reads the protected installation journal, checks installed DLL hashes, initializes COM on its worker, keeps a capture stream open and verifies the host callback before sending music. Captured voice is discarded, not added twice. Play runs the isolated native test when its development host is available, then starts playback using the installed host. Packaged builds without that test host still perform file and live-callback validation. There is no separate internal-test button or success message.

## Application packaging

`tools/build.ps1 -MixerBuild <validated-build-directory>` bundles only the production APO and producer DLL. The 0.11.10 release used `.tools/apo-prototype-10`; archive inspection confirmed matching production DLL hashes and no test DLL. The EXE also passed its component self-check. These checks do not perform a fresh attachment or prove remote VRChat playback.

`vrc/apo_install.py` finds the selected physical microphone, detects an already validated installation, and launches setup only after the UI's Install consent. Frozen apps dispatch `--mixer-setup` through their own EXE and exchange a report file with the setup helper. Setup requests administrator permission when needed; no separate driver download is used. The native attachment/rollback implementation is `vrc/apo_setup.py` below.

## Processing and transport

- One float32 microphone input and one identical-format output. No new microphone endpoint. Voice is passed through if there is no authorized music transport, the producer stops/crashes, or the channel layout/music sample rate is unsupported.
- Music transport is 48 kHz stereo float32. Mono microphones receive a stereo average. The prototype uses linear interpolation for other 8–192 kHz mono/stereo rates; resampling quality must be evaluated before release. Other layouts retain voice without music injection.
- Music is bounded to 100 ms in a shared ring, with one producer enforced by a named mutex and independent readers. Per-slot atomic sample/sequence operations detect overwrite races. No locks, allocation, file I/O or waits occur in the mixer callback. Shared storage is pinned before use; failure to pin falls back to voice.
- A configured audio-host instance creates `Global\VRCT.MicMusic.{token}`. The setup helper supplies a unique per-endpoint token and the authorized user's SID through the APO effects store. The DACL permits that user, SYSTEM and LocalService; the app only opens an existing mapping. Real Global transport and simultaneous capture clients passed the live test on this PC.
- Closing the producer disables music; an abandoned producer expires after 150 ms. Start creates a new generation so previous music is not replayed. Non-finite music samples are cleared and mixed output is clipped. Microphone gain is not changed.
- RAW/discovery initialization does not enable the music transport. There is no automatic bypass of disabled Windows audio enhancements or exclusive-mode capture.

Tests cover inactive passthrough, stereo mixing, independent readers, stopping, producer expiry, clipping, mono 44.1 kHz mixing, invalid samples, ring wrap, duplicate producers, COM lifecycle and cross-process transfer. These are standalone tests, **not proof that Windows/VRChat has loaded the APO**.

## Development setup and removal

`vrc/apo_setup.py` provides `plan`, `install`, `status` and `remove` commands. Installation requires administrator approval and the explicit `--development` flag. It refuses occupied stream/endpoint effect slots, disabled enhancements, conflicting registration and renamed test DLLs. It copies only the production APO and producer DLL into Program Files, writes a protected rollback journal before registry changes, attaches last, and opens microphone capture to verify real host callbacks. Validation failure rolls back the attachment. The optional `--restart-audio` restarts Audiosrv to rebuild cached graphs; no Secure Boot, code-integrity or protected-audio policy is changed.

Example, from an elevated shell in the project folder, after a read-only plan and standalone build checks:

```powershell
.venv-app/Scripts/python.exe -m vrc.apo_setup plan --endpoint <capture-endpoint-guid>
.venv-app/Scripts/python.exe -m vrc.apo_setup install --endpoint <capture-endpoint-guid> --microphone "<exact WASAPI microphone name>" --build .tools/apo-prototype-10 --development --restart-audio
.venv-app/Scripts/python.exe -m vrc.apo_setup status
.venv-app/Scripts/python.exe -m vrc.apo_setup remove --restart-audio
```

The tested HyperX capture endpoint is `{62b52006-a33c-453d-844f-8a1ece251538}` on this PC only. Do not reuse that identifier on another computer. `apo/remove_mixer.bat` runs removal with an administrator prompt. Backups are in `%ProgramData%\VRChat-Translator\MicrophoneMixer\attachment.json`; binaries are in `%ProgramFiles%\VRChatTranslatorMicMixer`. Removal restores only our changes and preserves later conflicting edits for review. It retains files and the journal.

Live tests: `apo/validate_microphone.py` verifies WAV injection; `--app` uses an isolated sound-playing process and waits for actual source audio before measuring injection. They send a quiet tone; other microphone clients may hear it. Reports contain tone amplitudes only, with no saved speech. Virtual Desktop measured approximately 0.0092 for WAV and 0.0080 for selected-app playback, falling below 0.00015 after Stop. This validates this PC's capture path, not a remote VRChat listener or other PCs.

With audio restart enabled, setup first validates the stream-effect attachment. If Windows does not activate it, setup restores that attempt and validates the unused legacy capture-effect slot. Failure of both restores the original endpoint properties. Journal validation accepts only the explicitly selected slot; it still refuses unrelated rollback paths. No driver replacement or Windows security policy change is needed.

## Remaining release work

1. Validate live Windows 10 loading/playback and other microphones. The API baseline is not an OS compatibility test.
2. Validate signed distribution and protected-content policy. The local unsigned development build loaded without weakening Windows policies; this is not a guarantee of universal unsigned deployment.
3. Test hot unplug, default-device changes, long playback, physical mute and bypass modes. Stop/crash fallbacks and registry rollback have automated tests; field behavior still needs broader coverage.
4. Decide how the translator's recognition should handle injected music, which can reach multiple microphone clients.
5. Validate fresh-PC installation and mixer upgrades through the bundled helper; provide a packaged removal flow. Current removal is the source `apo/remove_mixer.bat` helper. The [0.11.10 EXE/ZIP](https://github.com/SentoMinh/ART-Asia-realtime-Translator/releases/tag/v0.11.10) are published on GitHub; the EXE is not code-signed.

Microsoft references: [implementing APOs](https://learn.microsoft.com/en-us/windows-hardware/drivers/audio/implementing-audio-processing-objects), [APO architecture](https://learn.microsoft.com/en-us/windows-hardware/drivers/audio/audio-processing-object-architecture), [Windows 10/11 deployment](https://learn.microsoft.com/en-us/windows-hardware/drivers/dashboard/deploying-audio-processing-objects). This is our implementation; no Soundpad binaries or proprietary code are used.
