# ART – Asia realtime Translator

A small always-on-top window for VRChat (desktop mode) that:

- **hears other players** from VRChat or a selected audio output and shows their speech and translation in a scrolling chat log;
- **hears your microphone**, translates what you say and puts it in your VRChat chatbox;
- **translates text you type** and sends it to the chatbox;
- **mixes a running app's music into your physical microphone** using the optional development microphone mixer on Windows 11.

Version **0.11.9**. Enter your API URL and key under **Custom domain**, or choose local models.

Languages: English, Chinese (Mandarin), Cantonese, Vietnamese, Japanese and Korean. The window itself can be shown in English, 中文 or Tiếng Việt.

**It stays on your languages.** Auto-detect recognizes all six supported languages for translation. Other languages are checked for confidence before being announced with a line such as 【Speaking Spanish】. Uncertain speech is checked against the supported languages.

Historical measurements for English, Chinese and Vietnamese are in [BENCHMARK.md](BENCHMARK.md). They are not accuracy or latency guarantees for the current model selection, Japanese or Korean.

## Get the app and run it

1. Use a published ZIP or EXE, when available, downloaded from [Releases](https://github.com/SentoMinh/ART-Asia-realtime-Translator/releases). Extract a ZIP before opening its EXE. Python and the app libraries are bundled.
2. Run it. The first seconds are the program unpacking itself. Windows SmartScreen may warn because the program is not code-signed: "More info" → "Run anyway".
3. In VRChat turn OSC on: **Action Menu → Options → OSC → Enabled**. The light beside **VRChat** indicates status; hover for details.
4. Open **Settings (gear) → Models** and enter your API URL and key under **Custom domain**. Use **+** to add another domain and **−** to remove an added domain. Each domain has its own name, credentials and model choices; available models and account limits depend on your server. Click **Fetch models**, then **Save**. Pick a model below each Hearing and Translating domain selector; use **Connect** beside the selector to check the API.
5. Open **Settings → Sound → Microphone** and pick the microphone you use in VRChat.

VRChat has to run in windowed or borderless mode for the window to stay on top of it.

Builds use `VRChat-Translator-<version>.exe` or `VRChat-Translator-<version>-win64.zip`, with one package for everyone. Settings and provider keys stay in your Windows profile.

The packaged app checks GitHub for newer releases, downloads updates in the background, and applies them on the next start. No provider key is sent to GitHub. A source commit does not publish an application update. The old 0.9.15 EXE did not have an update source configured: download this release manually once to enable future automatic updates. Downloads come from [GitHub Releases](https://github.com/SentoMinh/ART-Asia-realtime-Translator/releases).

The setup script targets **Windows 10 1809+ / Windows 11 on Intel/AMD x64**. Run `install_windows.bat` if the Microsoft Visual C++ runtime is needed, or `install_windows.bat --check` for a read-only platform precheck. The script's microphone-permission reminder is general guidance, not detection of blocked access. Live Windows 10 testing remains outstanding. On Windows 10, speaker capture may include other apps sharing the audio output; selected-app music injection currently requires Windows 11.

### Models: who hears and who translates

| Service | Hears speech | Translates | Good to know |
|---|---|---|---|
| Local Model | ✓ SenseVoice or Whisper | ✓ NLLB-200 (CTranslate2) | download the chosen models; no API key |
| Custom domain | ✓ | ✓ | an OpenAI-compatible API address; add more with **+** |

The **Services** section lists only your custom domains. **Set up…** has a name, API address, key and **Fetch models**. Save the API settings, then select models below the Hearing and Translating domain selectors. **Connect** checks the selected API and shows **Connected** when it responds. Use **+** beside a row to add another domain, or **−** to remove an added one. The first domain remains available. Removing a selected domain switches that role back to the first domain. Previously selected, configured providers are preserved as custom domains when upgrading. Several translating models can be listed with commas for fallback.

Custom servers offering `nllb-200-ct2` use their `/translate` endpoint with explicit language codes; other translation models use `/chat/completions`.

**Custom domain → Set up…** fetches the available models. With an address entered, pasting a key automatically fetches the list after a short pause. Saving stores that domain’s list; changing its address or key invalidates the list. Click the down arrow in either Hearing or Translating model box to open its dropdown list. Choosing a model saves immediately. You can also type a model name when a server does not support discovery. Settings shows the model currently in use for each role.

Every normal startup checks configured APIs silently in the background. In **Settings → Models**, status moves from **Checking connection…** to **Online** or **Connection issue**, with a maximum 30-second wait per check. Hover for details. Saving a provider triggers another check. Unconfigured services are skipped. These are connection/authentication checks, not speech or translation requests; an online result does not guarantee that every model works. A missing model-list endpoint is reported as a connection issue; check the API base URL and server configuration.

### Local models: hearing and translation on your PC

Open **Settings → Models → Local Model → Set up…** and choose a model:

| Model | Job | Hardware and languages |
|---|---|---|
| Whisper large-v3-turbo | Hearing | NVIDIA GPU; includes Vietnamese. |
| Whisper large-v3 | Hearing | NVIDIA GPU; needs more memory than turbo. |
| SenseVoice Small | Hearing | CPU; Chinese, Cantonese, English, Japanese and Korean. Use Whisper for Vietnamese. |
| NLLB-200 · CTranslate2 | Translation | CPU, INT8; English, Vietnamese, Chinese, Cantonese, Japanese and Korean. |

All models are listed directly, each with a **Download** button, download size and progress. Downloads resume after interruptions and are checked before use. You can close the setup window while downloading. When the download finishes, that model activates for its job; **Use model** beside an installed model switches to it. Hearing and translation keep separate selections. Whisper shares the downloaded NVIDIA cuBLAS library between its two choices.

Local inference needs no API key. Select Local Model for both Hearing and Translating to run both steps on your PC. The first download needs internet access. Optional translation add-ons retain their existing fallback behavior.

## The window

| Part | What it does |
|---|---|
| VRChat + light | Compact status indicator; hover to see connection, OSC and capture details. |
| Mic / speaker buttons | Turn "my mic → chatbox" and "other players → subtitles" on or off. The bars show the sound level. |
| Arrows beside mic / speaker | Pick a microphone or subtitle audio source. The subtitle source list starts with VRChat, followed by available output devices. |
| Music icon | Select a running app, reload the source list, adjust volume, and use one Play/Stop button. Missing mixer setup asks for consent and administrator permission. See [Music setup](MUSIC_SETUP.md). |
| Wave button | Voice detector on/off. Off cuts the sound every 4 seconds instead of at the end of a sentence. |
| Globe | Language of the window. |
| Pin | Always on top. |
| I speak / They speak | Voice translation: pick one target and an optional second target beside **+**. Choose **None** to remove the second language. Other players' speech becomes subtitles in "I speak"; with two languages selected, their speech is detected automatically. |
| Text box + Send | Type, press Enter: translated and sent to the chatbox. The arrow picks the language for typed text independently of voice translation. Auto uses the last language heard, or "They speak" before anyone is heard (English if both are Auto). |

For example, set **I speak: English**, **They speak: Vietnamese**, and **Send: Chinese**. Your English microphone speech is translated into Vietnamese, Vietnamese players get English subtitles, and typed messages are translated into Chinese. Changing the Send language only changes typed messages.

In the current source, you can also select **Japanese** as the second "They speak" language. Each microphone message is sent once through OSC, with the original first, followed by the translations in selection order, each on its own line:

```text
Hello, how are you?
Xin chào, bạn khỏe không?
こんにちは、お元気ですか？
```

The second target is also available in **Settings → Translation → Second language**. Auto-detect remains available for the first target; if it resolves to the second target, only one translation is requested. Empty or identical text is omitted. If one translation fails, the original and successful translation still send, with an error in the app. Long messages share the [144-character OSC budget](https://docs.vrchat.com/docs/osc-as-input-controller#chatbox) across the lines. **Add my own words** controls original text for typed messages; microphone messages always include it. This change is not yet included in the 0.11.5 exports.

In **Settings → Translation**, turn on **Add Speaker words** to also send other players' speech to your own VRChat OSC chatbox as `translation (original)`. It uses the translation into **I speak**, independently of **Add my own words** and the Send language. The switch is off by default. Long messages shorten both parts as needed; turning it off also stops speaker messages waiting to be sent.

Click a line in the chat log to copy what was said (the original text, not the translation).

Drag the header, level meters or header labels to move the window. Header buttons distinguish clicks from dragging; native window movement has a manual fallback. This has automated coverage, but has not been tested live on Windows 10.

Existing saved API settings are retained where recoverable. If an older installation kept its URL only inside its EXE, enter that URL in Custom domain once; the new app cannot recover settings that were never saved outside the old program.

## Files it keeps

- `%APPDATA%\VRChat-Translator\ui.json` — settings; `models.json` — keys and chosen models in plain text under your Windows profile. The app does not encrypt them or apply a separate file ACL.
- `%APPDATA%\VRChat-Translator\addons\` — empty unless you add your own translator (below).
- `%LOCALAPPDATA%\VRChat-Translator\engine.log` — every sentence heard, its language, the translation and the delay. Look here first when nothing appears.
- `%LOCALAPPDATA%\VRChat-Translator\local-model\` — downloaded local model files; size depends on your choices. Deleting the folder frees the space; the program offers the downloads again.

What you type or say, and what other players say, is sent to the service picked in Settings → Models to be heard and translated.

### Your own translator (optional)

Any `.py` file in `%APPDATA%\VRChat-Translator\addons\` that defines `translators()` returning `(name, translator)` pairs is loaded at start. The chosen service's models are tried first, in their configured order; add-ons are fallback only if those models cannot answer. A translator has `prepare()` and `translate(text, target, likely_source="", heard=False) -> str`, and raises `vrc.translate.TranslateError` when it can't answer (the next one then takes over). Only put files there that you wrote or trust: they run as part of the program.

## Run from source

Python 3.12 and [uv](https://docs.astral.sh/uv/):

```
uv venv .venv-app --python 3.12
uv pip install --python .venv-app\Scripts\python.exe -r requirements.txt
run_ui.bat            (or: run_ui.bat --demo for example lines without VRChat)
```

- **Updates:** `run_ui.bat` first looks for a newer version on GitHub's `main` branch and installs it (`tools\update.py`), then opens the window. It skips the check when offline, when the folder is on a work branch, or while files in it are being edited, so nothing is ever overwritten. `set VRCT_NO_UPDATE=1` turns it off; every start writes one line to `%LOCALAPPDATA%\VRChat-Translator\update.log`.
- Tests: `.venv-app\Scripts\python -m pytest tests`
- Build the one-file program: `pwsh -File tools\build.ps1 -MixerBuild .tools\apo-prototype-10` (use your validated native build directory; see [APO build instructions](apo/README.md)). `-Folder` builds a folder and ZIP. Without `-MixerBuild`, native mixer DLLs are not explicitly included by the build command.
- Check a build: `VRChat-Translator.exe --selfcheck` writes `%LOCALAPPDATA%\VRChat-Translator\selfcheck.txt`

Source validation for 0.11.9: **400 tests passed**, plus actual CPU inference with SenseVoice on a sample recording and NLLB translating English to Vietnamese. The EXE includes the local runtimes and microphone mixer. Whisper large-v3 has not been tested with downloaded weights on a GPU.

Historical 0.11.5 checks covered automated tests, packaged self-checks, source/bundled-code privacy scans, and ZIP/checksum verification. A new package must be verified separately. These checks do not establish fresh-PC installation, live Windows 10 behavior or Japanese/Korean recognition accuracy with real services.

## Layout

- `ui\` — the window (PySide6): main window, settings, chat log, the three window languages.
- `vrc\` — VRChat itself: finding it, the chatbox (OSC), sound capture, text translation.
- `engine\` — speech: voice detector → sentences → speech-to-text (online or local Whisper/SenseVoice) → translation (online or local NLLB). `engine\services.py` lists the services.
- `apo\` — native microphone mixer and development validation/removal tools; `driver\` retains the earlier unused virtual-microphone prototype.
- [MUSIC_SETUP.md](MUSIC_SETUP.md) — music routing and current compatibility limits; [CODEBASE.md](CODEBASE.md) — developer map and verification status.
- [BENCHMARK.md](BENCHMARK.md) — how the speech and translation models were chosen.
- `tests\`, `tools\` — tests, the build script, a tool that draws the window to PNG.
