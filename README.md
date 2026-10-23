# ART – Asia realtime Translator

A small always-on-top window for VRChat (desktop mode) that:

- **hears other players** from VRChat or a selected audio output and shows their speech and translation in a scrolling chat log;
- **hears your microphone**, translates what you say and puts it in your VRChat chatbox;
- **translates text you type** and sends it to the chatbox;
- **mixes a running app's music into your physical microphone** using the optional development microphone mixer on Windows 11.

Version **[0.12.6](https://github.com/SentoMinh/ART-Asia-realtime-Translator/releases/tag/v0.12.6)**. Enter your API URL and key under **Custom domain**, or choose local models.

See the [change log](CHANGELOG.md) for implementation details, measurements and troubleshooting notes.

For an Obsidian-ready explanation of the whole project, open [ART Project Guide](ART%20Project%20Guide.md): architecture diagrams, language controls, model storage, folder map, build/update flow and troubleshooting.

Local models now include PhoWhisper Small for Vietnamese hearing and Qwen3 1.7B INT8 for translation. NLLB remains the low-latency default. See [the model plan and checks](LOCAL_TRANSLATION_PLAN.md).

Since version 0.12.4, ART sends your chatbox messages in all selected **They speak** languages. Choose **Custom languages** under Settings → Translation → Chatbox languages to use separate destinations.

Languages: English, Chinese (Mandarin), Cantonese, Vietnamese, Japanese and Korean. The window itself can be shown in English, 中文 or Tiếng Việt.

**It stays on your languages.** Auto-detect recognizes all six supported languages for translation. Other languages are checked for confidence before being announced with a line such as 【Speaking Spanish】. Uncertain speech is checked against the supported languages.

Historical measurements for English, Chinese and Vietnamese are in [BENCHMARK.md](BENCHMARK.md). They are not accuracy or latency guarantees for the current model selection, Japanese or Korean.

## Get the app and run it

1. Download the EXE or ZIP from [v0.12.6](https://github.com/SentoMinh/ART-Asia-realtime-Translator/releases/tag/v0.12.6). Extract a ZIP before opening its EXE. Python and the app libraries are bundled.
2. Run it. The first seconds are the program unpacking itself. Windows SmartScreen may warn because the program is not code-signed: "More info" → "Run anyway".
3. In VRChat turn OSC on: **Action Menu → Options → OSC → Enabled**. The light beside **VRChat** indicates status; hover for details.
4. Open **Settings (gear) → Models** and enter your API URL and key under **Custom domain**. Use **+** to add another domain and **−** to remove an added domain. Each domain has its own name, credentials and model choices; available models and account limits depend on your server. Click **Fetch models**, then **Save**. Click **▼** in the model box below each Hearing and Translating domain selector to pick a model; use **Connect** beside the selector to check the API.
5. Open **Settings → Sound → Microphone** and pick the microphone you use in VRChat.

VRChat has to run in windowed or borderless mode for the window to stay on top of it.

Builds use `VRChat-Translator-<version>.exe` or `VRChat-Translator-<version>-win64.zip`, with one package for everyone. Settings and provider keys stay in your Windows profile.

The packaged app checks GitHub for newer releases, downloads updates in the background, and applies them on the next start. A “What’s new” panel appears inside the overlay once per version, including the first start of this release. The app saves the shown version in `ui.json`, so restarting does not repeat it. No provider key is sent to GitHub. A source commit does not publish an application update. The old 0.9.15 EXE did not have an update source configured: download this release manually once to enable future automatic updates. Downloads come from [GitHub Releases](https://github.com/SentoMinh/ART-Asia-realtime-Translator/releases).

The setup script targets **Windows 10 1809+ / Windows 11 on Intel/AMD x64**. Run `install_windows.bat` if the Microsoft Visual C++ runtime is needed, or `install_windows.bat --check` for a read-only platform precheck. The script's microphone-permission reminder is general guidance, not detection of blocked access. Live Windows 10 testing remains outstanding. On Windows 10, speaker capture may include other apps sharing the audio output; selected-app music injection currently requires Windows 11.

### Models: who hears and who translates

| Service | Hears speech | Translates | Good to know |
|---|---|---|---|
| Local Model | ✓ SenseVoice or Whisper | ✓ NLLB-200 (CTranslate2) | download the chosen models; no API key |
| Custom domain | ✓ | ✓ | an OpenAI-compatible API address; add more with **+** |

The **Services** section lists only your custom domains. **Set up…** opens inside Settings with a name, API address, key and **Fetch models**. It moves with Settings; Close or Cancel returns to the Models page. Navigation is disabled while a setup panel is open. Save the API settings, then select models below the Hearing and Translating domain selectors. **Connect** checks the selected API and shows **Connected** when it responds. Use **+** beside a row to add another domain, or **−** to remove an added one. The first domain remains available. Removing a selected domain switches that role back to the first domain. Previously selected, configured providers are preserved as custom domains when upgrading. Several translating models can be listed with commas for fallback.

Custom servers offering `nllb-200-ct2` use their `/translate` endpoint with explicit language codes; other translation models use `/chat/completions`.

**Custom domain → Set up…** fetches the available models. With an address entered, pasting a key automatically fetches the list after a short pause. Saving stores that domain’s list; changing its address or key invalidates the list. Click the down arrow in either Hearing or Translating model box to open its dropdown list. Choosing a model saves immediately. You can also type a model name when a server does not support discovery. Settings shows the model currently in use for each role.

Every normal startup checks configured APIs silently in the background. In **Settings → Models**, status moves from **Checking connection…** to **Online** or **Connection issue**, with a maximum 30-second wait per check. Hover for details. Saving a provider triggers another check. Unconfigured services are skipped. These are connection/authentication checks, not speech or translation requests; an online result does not guarantee that every model works. A missing model-list endpoint is reported as a connection issue; check the API base URL and server configuration.

### Local models: hearing and translation on your PC

Open **Settings → Models → Local Model → Set up…** and choose a model:

| Model | Job | Hardware and languages |
|---|---|---|
| Whisper large-v3-turbo | Hearing | Fast NVIDIA GPU option; English, Chinese, Cantonese, Vietnamese, Japanese and Korean. Multilingual conversations; mixed sentences can still be misheard. |
| SenseVoice Small | Hearing | Lightweight CPU option; Chinese, Cantonese, English, Japanese and Korean. Automatic detection; no Vietnamese. Mixed-language accuracy varies. |
| PhoWhisper Small | Hearing | Vietnamese specialist trained on diverse accents. CPU INT8, no NVIDIA needed; may be slower than GPU turbo. About 0.9 GiB download. |
| NLLB-200 · CTranslate2 | Translation | CPU INT8; all six app languages. Default for low latency. |
| Qwen3 1.7B · INT8 | Translation | Optional CPU language model for all six app languages, thinking disabled. About 1.6 GiB download. Slower than NLLB in our replay; wording and Cantonese quality need comparison. |

The download panel opens inside Settings and moves with it. Its model list has one scrollbar; the title and single Close button stay at the top. All models are listed directly, each with a **Download** button, download size and progress. Downloads resume after interruptions and are checked before use. You can close the setup window while downloading. When the download finishes, that model activates for its job; **Use model** beside an installed model switches to it. Hearing and translation keep separate selections. Only Whisper turbo requires NVIDIA libraries. Non-turbo Whisper large-v3 is removed from the list; an old selection falls back to turbo without deleting its downloaded files. Existing hearing and translation choices otherwise stay unchanged. Switching translators releases the previous model before loading the next.

**Free disk space:** click **Delete → Confirm delete** on a model card, or Cancel to keep it. This removes app-managed weights and partial downloads; shared NVIDIA libraries, other models and your settings stay intact. Deletion is disabled during downloads. Leftover non-turbo large-v3 files get a cleanup-only card. External Hugging Face caches and loaded model memory are not removed. If a file is in use, stop using the model/restart ART and retry. Available models can be downloaded again.

Local inference needs no API key. Select Local Model for both Hearing and Translating to run both steps on your PC. The first download needs internet access. Optional translation add-ons retain their existing fallback behavior.

**Since 0.12.5:** Hugging Face model downloads automatically try [HF-Mirror](https://hf-mirror.com/) if the original connection fails or refuses the file. Resume and the original SHA-256 checks remain enabled. Other download hosts are unchanged. A small-file test redirected back to Hugging Face; availability from mainland China is not guaranteed. See [AGENT_HANDOFF.md](AGENT_HANDOFF.md) for release status and remaining checks.

**Cannot download NLLB from China or another restricted network?** Use the [offline NLLB package](https://github.com/SentoMinh/ART-Asia-realtime-Translator/releases/download/v0.12.3/ART-NLLB-200-CT2-offline.zip) (about 558 MiB; [SHA-256](https://github.com/SentoMinh/ART-Asia-realtime-Translator/releases/download/v0.12.3/ART-NLLB-200-CT2-offline.zip.sha256)). Download it on a working connection or transfer the ZIP by USB or a file-sharing service. Close ART, extract the ZIP, and double-click **Install-NLLB.cmd**. Then open Settings → Models, select **Local Model** for Translating, and choose **Use model** for NLLB. No administrator, Python, Hugging Face connection or API key is needed during installation. The installer checks the four pinned model files and preserves any replaced folder as a backup. It works with v0.12.3; the app EXE is unchanged. GitHub access from mainland China is not verified, so file transfer is the fallback if that download is also unavailable. The model remains [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/); attribution is included in the ZIP.

## The window

| Part | What it does |
|---|---|
| Move to VRChat button | Beside the VRChat label: detects the visible game window and moves the translator to the top-left of its content area. Open or restore VRChat first. This moves once per click and preserves the overlay size. |
| VRChat + light | Compact status indicator; hover to see connection, OSC and capture details. |
| Mic / speaker buttons | Turn "my mic → chatbox" and "other players → subtitles" on or off. The bars show the sound level. |
| Arrows beside mic / speaker | Pick a microphone or subtitle audio source. The subtitle source list starts with VRChat, followed by available output devices. |
| Music icon | Select a running app, reload the source list, adjust volume, and use one Play/Stop button. Missing mixer setup asks for consent and administrator permission. See [Music setup](MUSIC_SETUP.md). |
| Wave button | Voice detector on/off. Off cuts the sound every 4 seconds instead of at the end of a sentence. |
| Globe | Language of the window. |
| Pin | Always on top. |
| I speak / They speak | Check up to three spoken languages in each dropdown. With multiple choices, recognition detects the language and ignores results outside your selection. They speak also offers Auto-detect as a separate choice. |
| Translated to | Check up to three translation languages to show on the panel for microphone speech, other players and typed messages. Each output is labeled with its language. |
| Text box + Send | Type, press Enter: translated and sent to the chatbox. Auto follows Chatbox languages; the arrow can override this with one language for typed text only. The button shows the current destinations. |

For example, set **I speak: English**, **They speak: Chinese, Vietnamese**, and **Translated to: English, Chinese, Vietnamese**. Your microphone sends original English, Chinese and Vietnamese as separate lines in one VRChat message. **Translated to** controls only the panel. **Settings → Translation → Chatbox languages** defaults to **Follow 'They speak'**, or choose **Custom languages** (up to three). When They speak uses Auto-detect, chatbox messages follow the last language heard, falling back to English before anyone is heard. Typed messages use the first I speak language as their source; an explicit Send language overrides chatbox choices for typed messages only.

The same three pickers are available in **Settings → Translation**. At least one choice stays selected in each box. Existing settings default to following They speak. Destinations are captured when each message starts. Shared panel/chatbox translations are requested once, and a target matching the source reuses the original. Successful translations survive a failed target; if all chatbox targets fail, the original is sent. Duplicate text lines are removed. Microphone messages include the original plus up to three translations, sharing one 144-character budget; long lines are shortened while keeping space for every language. **Add my own words** controls original text for typed messages. Each completed panel translation appears while the remaining languages continue. Additional distinct targets add translation work and can delay the complete chatbox message; no extra OSC messages or parallel inference jobs are introduced.

In **Settings → Translation**, turn on **Add Speaker words** to also send other players' speech to your own VRChat OSC chatbox as `translation (original)`. It uses the first **Translated to** language, independently of **Add my own words** and the Send language. The switch is off by default. Long messages shorten both parts as needed; turning it off also stops speaker messages waiting to be sent.

Click a line in the chat log to copy what was said (the original text, not the translation).

Drag the top controls, level meters or header labels to move the window. Drag the standard resize grip in the bottom-right corner to change width and height. The top edge and top corners also resize; other side and bottom edges do not. The corner grip remains available below 30% darkness and when the top controls are hidden. Header buttons distinguish clicks from dragging; native window movement has a manual fallback.

Version 0.11.11 fixes the disappearing body background at the 29–30% boundary. In **Settings → Appearance → Background darkness**, values below **30%** let clicks pass through empty overlay space while preserving the selected background darkness. Click a subtitle to copy its original text, or drag over original/translated text to copy only the selection on release (Ctrl+C also works). The typing box and top controls stay usable. At **30%** or above, the full panel accepts clicks again. This was checked against a separate Windows application; live VRChat and Windows 10 behavior still need testing.

Existing saved API settings are retained where recoverable. If an older installation kept its URL only inside its EXE, enter that URL in Custom domain once; the new app cannot recover settings that were never saved outside the old program.

## Files it keeps

- `%APPDATA%\VRChat-Translator\ui.json` — settings; `models.json` — API addresses, keys, chosen models and fetched model lists in plain text under your Windows profile. The app does not encrypt them or apply a separate file ACL.
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

Release validation for 0.11.10: **422 tests passed**, including the 30% click-through threshold, top-only resize edges, embedded setup panels and once-per-version update notices. Windows checks also verified actual mouse-drag resizing with the top grip, cross-process click-through, retained text/input interaction and subtitle copying, and window detection/placement against a separate test application. The EXE passed its packaged self-check, bundled-runtime and native-DLL checks, source/artifact scans, ZIP checks and SHA-256 verification. The GitHub download, replacement and restart from 0.11.9 to 0.11.10 were verified, followed by a no-update check on the current version.

The 0.12.5 source passed 505 tests. Real pinned PhoWhisper and Qwen files loaded and ran on CPU; two Vietnamese recording replays and short multilingual translation checks are recorded in LOCAL_TRANSLATION_PLAN.md and LATENCY_REPORT.md. This is not a broad quality evaluation. Fresh-PC installation, Windows 10 behavior and mainland-China download access remain unverified.

## Layout

- `ui\` — the window (PySide6): main window, settings, chat log, the three window languages.
- `vrc\` — VRChat itself: finding it, the chatbox (OSC), sound capture, text translation.
- `engine\` — speech: voice detector → sentences → speech-to-text (online or local Whisper/SenseVoice) → translation (online or local NLLB). `engine\services.py` lists the services.
- `apo\` — native microphone mixer and development validation/removal tools; `driver\` retains the earlier unused virtual-microphone prototype.
- [MUSIC_SETUP.md](MUSIC_SETUP.md) — music routing and current compatibility limits; [CODEBASE.md](CODEBASE.md) — developer map and verification status.
- [BENCHMARK.md](BENCHMARK.md) — how the speech and translation models were chosen.
- `tests\`, `tools\` — tests, the build script, a tool that draws the window to PNG.

## Project priorities

Voice recognition is the current focus. Identifying individual speakers as Speaker 1 / Speaker 2 is deferred. See [ROADMAP.md](ROADMAP.md) for the saved plan to revisit during future feature discussions.
