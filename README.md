# VRChat Translator

A small always-on-top window for VRChat (desktop mode) that:

- **hears VRChat or a selected audio output device** and shows what was said with a translation, as a scrolling chat log;
- **hears your microphone**, translates what you say and puts it in your VRChat chatbox;
- **translates text you type** and sends it to the chatbox.

Languages: English, Chinese (Mandarin), Cantonese, Vietnamese. The window itself can be shown in English, 中文 or Tiếng Việt.

**It stays on your languages.** On Auto-detect, the program only believes someone speaks another language when the speech model is at least 80% sure. Then it does not translate; it writes one line such as 【Speaking Korean】. Half-heard words and noise are taken as the language of yours that fits best, instead of turning into Spanish or Japanese lines.

**How well it works:** a translated line appears 1.2–2.2 s after a player stops talking; 94–96% of words heard right on a clean microphone, 88–93% over loud music. All measurements are in [BENCHMARK.md](BENCHMARK.md).

## Download and run (Windows 10 1809+ or Windows 11, x64)

1. Download `VRChat-Translator-Public-<version>-win64.zip` when available on the [Releases](https://github.com/SentoMinh/vrchat-translator-public/releases) page and extract it. Source code archives are not the Windows app.
2. Run `install_windows.bat` to install the Microsoft Visual C++ runtime, then open the Public EXE. Python and app libraries are bundled. The EXE is not code-signed; only run downloads you trust.
3. In VRChat turn OSC on: **Action Menu → Options → OSC → Enabled**. The dot in the window turns green ("Connected").
4. Open **Settings (gear) → Models** and set up a service with **your own key** (below). The program starts with **Google Gemini** for both hearing and translating: its key is free, with a small daily allowance. **Set up… → Get a key**, paste it, **Save**.
5. Use the arrow to the left of the microphone icon to pick your microphone. Use the arrow to the left of the speaker icon to select **VRChat** or an output device. Choosing an output device captures all apps playing through it.

VRChat has to run in windowed or borderless mode for the window to stay on top of it.

This repository contains the **Public edition**, which uses your own API keys. Download future EXE updates manually from Releases. Each published version is tagged so its source can be restored later.

Component checks ran on Windows 11; a real Windows 10 run has not been verified. On Windows 10, the VRChat capture library can fall back to capturing the default output device, including other apps. Installing dependencies does not add process-specific capture support.

### Models: who hears and who translates

| Service | Hears speech | Translates | Good to know |
|---|---|---|---|
| OpenAI | ✓ Whisper | ✓ GPT | paid per use |
| Google Gemini | ✓ | ✓ | the benchmark's best translator; a small free daily allowance |
| Qwen (Alibaba Cloud) | ✓ Qwen3-ASR | ✓ | tells Cantonese from Mandarin by itself |
| Xiaomi MiMo | – | ✓ | low prices |
| OpenRouter | ✓ | ✓ | one key for many models, Qwen and MiMo among them |
| Custom | ✓ | ✓ | any OpenAI-compatible address, e.g. a Whisper server on your own PC |

Each service's **Set up…** window has the key, the models (empty = the default shown), a **Get a key** link and a **Test** button. Several translating models can be listed with commas: when one reaches its limit, the next one answers.

**Custom domain** also has **Fetch models** and hearing/translation model pickers. The Models page displays the selected hearing model and the latest successful translation model, or the configured default before the first request.

### What the downloaded program does not include

The **Local Model** (Whisper on your own graphics card) needs faster-whisper and NVIDIA's GPU libraries (2 GB), which are not in the download; to use it, run from source (below) on a PC with an NVIDIA card, and pick it in Settings → Models → Hearing.

## The window

| Part | What it does |
|---|---|
| Dot + text | Green "Connected", orange "OSC is off" / "No game sound", red "VRChat not found". Hover for details. |
| Mic / speaker buttons | Turn "my mic → chatbox" and "other players → subtitles" on or off. The bars show the sound level. |
| Arrows beside mic / speaker | Choose a microphone input or the subtitle audio source. VRChat is first in the speaker menu, followed by output devices. Choices are saved. |
| Wave button | Voice detector on/off. Off cuts the sound every 4 seconds instead of at the end of a sentence. |
| Globe | Language of the window. |
| Pin | Always on top. |
| I speak / They speak | Voice translation: your microphone goes from "I speak" into "They speak"; other players' speech becomes subtitles in "I speak". Auto-detect follows the last player's language; pick Cantonese for Cantonese speakers. |
| Text box + Send | Type, press Enter: translated and sent to the chatbox. The arrow picks the language for typed text independently of voice translation. Auto uses the last language heard, or "They speak" before anyone is heard (English if both are Auto). |

For example, set **I speak: English**, **They speak: Vietnamese**, and **Send: Chinese**. Your English microphone speech is translated into Vietnamese, Vietnamese players get English subtitles, and typed messages are translated into Chinese. Changing the Send language only changes typed messages.

In **Settings → Translation**, turn on **Add Speaker words** to also send other players' speech to your own VRChat OSC chatbox as `translation (original)`. It uses the translation into **I speak**, independently of **Add my own words** and the Send language. The switch is off by default. Long messages shorten both parts as needed; turning it off also stops speaker messages waiting to be sent.

Click a line in the chat log to copy what was said (the original text, not the translation).

## Files it keeps

- `%APPDATA%\VRChat-Translator\ui.json` — settings; `models.json` — your keys and chosen models (plain text, readable only by your Windows account).
- `%APPDATA%\VRChat-Translator\addons\` — empty unless you add your own translator (below).
- `%LOCALAPPDATA%\VRChat-Translator\engine.log` — every sentence heard, its language, the translation and the delay. Look here first when nothing appears.

What you type or say, and what other players say, is sent to the service picked in Settings → Models to be heard and translated.

### Your own translator (optional)

Any `.py` file in `%APPDATA%\VRChat-Translator\addons\` that defines `translators()` returning `(name, translator)` pairs is loaded at start, and its translators are tried before the chosen service's. A translator has `prepare()` and `translate(text, target, likely_source="", heard=False) -> str`, and raises `vrc.translate.TranslateError` when it can't answer (the next one then takes over). Only put files there that you wrote or trust: they run as part of the program.

## Run from source

Python 3.12 and [uv](https://docs.astral.sh/uv/):

```
uv venv .venv-app --python 3.12
uv pip install --python .venv-app\Scripts\python.exe -r requirements.txt
run_ui.bat            (or: run_ui.bat --demo for example lines without VRChat)
```

- **Updates:** `run_ui.bat` first looks for a newer version on GitHub's `main` branch and installs it (`tools\update.py`), then opens the window. It skips the check when offline, when the folder is on a work branch, or while files in it are being edited, so nothing is ever overwritten. `set VRCT_NO_UPDATE=1` turns it off; every start writes one line to `%LOCALAPPDATA%\VRChat-Translator\update.log`.
- Tests: `.venv-app\Scripts\python -m pytest tests`
- Build the one-file program: `pwsh -File tools\build.ps1` (output in `dist\`; `-Folder` builds a folder and a zip instead, which starts a little faster)
- Check a build: `VRChat-Translator.exe --selfcheck` writes `%LOCALAPPDATA%\VRChat-Translator\selfcheck.txt`

## Layout

- `ui\` — the window (PySide6): main window, settings, chat log, the three window languages.
- `vrc\` — VRChat itself: finding it, the chatbox (OSC), sound capture, text translation.
- `engine\` — speech: voice detector → sentences → speech-to-text (an online service or local Whisper) → translation. `engine\services.py` lists the services.
- [BENCHMARK.md](BENCHMARK.md) — how the speech and translation models were chosen.
- `tests\`, `tools\` — tests, the build script, a tool that draws the window to PNG.
