# Music to microphone

The current source app and published EXE use our own Windows microphone mixer (APO). It adds music to the selected physical microphone; no virtual cable or separate virtual microphone is used.

The mixer attaches to one microphone at a time. If it is already attached to another device, version 0.12.3 shows that device and a **Use [microphone]** button. This selects and saves that microphone in the translator; select the same device in VRChat. The app checks the installed files, registration and active endpoint before switching. It does not reinstall or move the mixer when this button is used.

The error **“A mixer registration already exists. Remove it using its backup first.”** in older versions can mean the mixer is healthy on a different microphone. For example, a mixer attached to Virtual Desktop Audio cannot be installed again on HyperX QuadCast without removing the existing attachment first. Changing the translator microphone alone does not move the Windows mixer. If you intend to move it, use the saved rollback journal to remove the old attachment before installing on the new microphone; do not delete its registration manually.

Setup tries the unused legacy capture-effect slot if stream-effect validation fails, with rollback if neither works. The music panel warns when the active VRChat session log identifies a different microphone; unavailable or ambiguous logs are treated as unknown. Fresh-PC installation remains untested.

Opening Music with a missing mixer offers **Install**, with the Windows administrator shield. After consent, the setup helper checks the selected microphone, requests UAC approval when setup is needed and opens a setup console. Builds made with `-MixerBuild` bundle the native mixer and setup launcher; those builds need no separate driver download. Source builds use their local native build. Installation briefly restarts Windows audio. Existing validated installations are detected without reinstalling. Declining UAC leaves setup off; failures are shown in the dialog. The mixer remains a development build, with clean-machine installation and Windows 10 live testing still outstanding.

## Try it now

1. Open the released translator EXE and click its music button. For source development, use [apo/open_music.bat](apo/open_music.bat) for the standalone music window.
2. Select the same microphone in VRChat and the translator. Use the device named by the installed-mixer message, or the microphone you installed the mixer on. A source app must also be selected before Play becomes available.
3. Under **Music source**, select Spotify, your browser, or another running app, then click **▶**. Use the reload icon beside the source picker if you opened the app afterward. Start playback in that app as usual.
4. Play checks the mixer before sending audio. Successful checks stay hidden; failures show an error and prevent playback. Adjust **Music volume** as needed. The same button becomes **■** to stop playback or cancel a pending check. Closing the panel keeps music running; Stop or closing the entire translator ends playback. Your ordinary microphone remains available.

The dialog offers app audio only, currently requiring Windows 11. WAV playback remains available to development validation tools, but is not an option in the dialog.

The music is sent to apps using this microphone, including potentially the translator's own speech recognition. Browser capture includes the browser's process tree, not only one tab. Neither this feature nor Stop music changes VRChat's mute or push-to-talk controls.

The **Source audio** meter shows audio being sent into the mixer, before the music volume control. Silence is reported instead of claiming music is playing. It does not prove that Discord or VRChat receives the processed microphone.

For Discord testing, select **Studio** instead of **Voice Isolation**, then use **Mic Test**. If music is still missing, select **Custom** and turn off **Bypass System Audio Input Processing**, noise suppression and echo cancellation. Bypassing Windows input processing can skip this microphone effect entirely. Keep the attached microphone selected and reopen Discord after installation if necessary.

Windows audio was restarted during installation. If an already-running audio app stopped capturing, reopen it.

## Remove the development attachment

Run [apo/remove_mixer.bat](apo/remove_mixer.bat). It requests administrator approval, restores the affected registry values from the saved journal, and briefly restarts Windows audio. It preserves the existing Voice Clarity component. Mixer DLLs and the journal are retained for diagnostics; no recursive file removal occurs.

## Tests and compatibility

When the development test host is available, **▶** first runs its isolated native test. This test does not play audible sound or install the mixer. Playback also validates the installed mixer files and waits for the actual microphone callback before sending audio; these live checks still run in builds without the standalone test host. A successful check does not prove that Discord or VRChat receives the processed microphone.

The live verification scripts below send a quiet test tone that apps using the microphone may hear. Captured voice stays in memory and is never saved:

```powershell
.venv-app/Scripts/python.exe apo/validate_microphone.py
.venv-app/Scripts/python.exe apo/validate_microphone.py --app
```

The native API target includes Windows 10. WAV playback does not need Windows 11 process capture, but live Windows 10 testing remains outstanding. Selected-app capture currently requires Windows 11. Physical mute behavior, device hotplug, other microphone drivers and public signed deployment still need validation.

See [apo/README.md](apo/README.md) for build and setup details. The earlier kernel-driver prototype remains in [driver/](driver/) for reference.
