# Music to microphone

The current source app and 0.11.5 exports use our own Windows microphone mixer (APO). It adds music to the selected physical microphone; no virtual cable or separate virtual microphone is used.

**The current development attachment is on Microphone (Virtual Desktop Audio).** VRChat used that headset microphone while the translator previously sent music to HyperX QuadCast. The attachment and translator selection now match the headset. Virtual Desktop did not load the stream-effect slot, but its legacy capture-effect slot passed live callback, WAV and selected-app injection tests. The HyperX attachment was removed and both microphones' existing Microsoft Voice Clarity references were preserved. Remote VRChat reception still needs a listener check. This is not a released installer or a Windows 10 certification claim.

This compatibility fix is in source; the existing 0.11.5 EXEs do not include it. Use the source launcher below until a new export is approved. Setup now tries the unused legacy capture-effect slot if stream-effect validation fails, with rollback if neither works. The music panel warns when the active VRChat session log identifies a different microphone; unavailable or ambiguous logs are treated as unknown.

Opening Music with a missing mixer offers **Install**, with the Windows administrator shield. After consent, the setup helper checks the selected microphone, requests UAC approval when setup is needed and opens a setup console. Builds made with `-MixerBuild` bundle the native mixer and setup launcher; those builds need no separate driver download. Source builds use their local native build. Installation briefly restarts Windows audio. Existing validated installations are detected without reinstalling. Declining UAC leaves setup off; failures are shown in the dialog. The mixer remains a development build, with clean-machine installation and Windows 10 live testing still outstanding.

## Try it now

1. Use [apo/open_music.bat](apo/open_music.bat) for the corrected standalone source music window, or run the translator from source and click its music button.
2. Select the same microphone in VRChat and the translator. **Microphone (Virtual Desktop Audio)** is currently attached on the development PC. HyperX QuadCast was previously validated; other microphones still need live validation.
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
