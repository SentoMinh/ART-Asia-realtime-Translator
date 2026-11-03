# ART – Asia realtime Translator

**[Download the latest release](https://github.com/SentoMinh/ART-Asia-realtime-Translator/releases/latest)** · Windows 10 1809+ / Windows 11 · x64

ART is a desktop overlay for VRChat that turns speech into text, translates it, and sends your voice or typed messages to the VRChat chatbox. It can also show subtitles on a SteamVR wrist panel.

## What it does

- **Hears other players** from VRChat or a selected audio output and shows their speech plus translations in a scrolling chat log.
- **Hears your microphone**, translates what you say, and sends it to the VRChat chatbox.
- **Translates typed text** and sends it with the current language choices.
- **Mixes a running app's music** into your microphone on Windows 11 with the optional mixer.
- **Shows the chat log on your wrist** when SteamVR is running.

## What's new in 1.1.0

- First launch asks for **English, 中文 or Tiếng Việt** and uses that language for setup and the guided manual.
- **Local AI is the default**: Whisper large-v3-turbo and NLLB-200 are recommended and selected immediately.
- **Self-hosted setup** accepts a URL, optional API key, fetches the model list, and saves the server by name under **Services/API**.
- The **guided manual** highlights each control, supports Skip/Next, and lets you click the highlighted button.
- **Settings** stays beside the pin; toolbar utilities moved into the **More actions** arrow.
- The music dialog warns when very loud music can affect translation.

Earlier changes are in [CHANGELOG.md](CHANGELOG.md).

## Requirements

- 64-bit Windows 10 version 1809 or newer, or Windows 11.
- VRChat in desktop mode, windowed or borderless if you want the overlay above the game.
- A microphone for voice input; VRChat OSC enabled for chatbox messages.
- The release EXE/ZIP includes Python, Qt and the Microsoft Visual C++ runtime libraries. **No separate setup script is needed.**
- Local models download on first use. An NVIDIA GPU is optional; the app also runs local models on CPU, and AMD Vulkan Whisper is available on compatible drivers.

## Quick start

1. Download the EXE or ZIP from the [latest release](https://github.com/SentoMinh/ART-Asia-realtime-Translator/releases/latest). If you use the ZIP, extract it first.
2. Open `VRChat-Translator-<version>.exe`. Windows SmartScreen may warn because the build is not code-signed: **More info → Run anyway**.
3. In VRChat, enable **Action Menu → Options → OSC → Enabled**.
4. Complete the first-run language screen and setup, then follow the short manual. You can skip either screen.
5. Open **Settings (gear)** to choose models, microphone, subtitles and chatbox options.

The VRChat status light and tooltip show whether the game and OSC were found.

## First-run setup

### Local AI

Local models are selected by default:

- **Hearing:** Whisper large-v3-turbo (NVIDIA) or Whisper turbo · Vulkan (AMD), with SenseVoice and PhoWhisper alternatives.
- **Translating:** NLLB-200, with Qwen3 1.7B and Hy-MT2 1.8B as alternatives.

Whisper large-v3-turbo and NLLB-200 are marked **Recommended**. The GPU build that does not match the PC is disabled. Chosen models are equipped immediately; downloads continue in the background.

### Self-hosted / Online models

Select **Self-hosted** to use an OpenAI-compatible server:

1. Enter the server address, for example `https://your-server.example/v1`.
2. Add an API key if the server requires one.
3. Click **Fetch models**.
4. Pick **Hearing model** and **Translating models**.
5. Give the service a name in the small save window.

The named service is stored in **Settings → Services/API** with its URL, key and model choices. Changing the model dropdowns updates the saved service.

## Main window

| Control | What it does |
|---|---|
| VRChat status | Connection, OSC and capture status; hover for details. |
| Microphone arrow + mic button | Choose the input device and turn **my mic → chatbox** on or off. |
| Speaker arrow + speaker button | Choose the subtitle source and turn **other players → subtitles** on or off. |
| **More actions** arrow | Move to VRChat, music, voice detector, window language, VR and clear chat. |
| **Pin** | Keep the window above the game. |
| **Gear** (beside the pin) | Open Settings. |
| I speak / They speak / Translated to | Pick up to three languages for each role. |
| Text box + Send | Type a message, press Enter, and send the translation. The arrow beside Send chooses the typed-text target. |
| Minimise / Maximise / Close | Standard window controls. |

The manual does not cover the three window-control buttons, and highlighted controls can be clicked while it is open.

## Models and services

### Local models

| Model | Job | Notes |
|---|---|---|
| Whisper large-v3-turbo | Hearing | Fast NVIDIA option; the six app languages. |
| Whisper turbo · Vulkan (AMD) | Hearing | whisper.cpp/Q5; Vulkan-compatible AMD GPUs. |
| SenseVoice Small | Hearing | Lightweight CPU option; no Vietnamese. |
| PhoWhisper Small | Hearing | Vietnamese specialist; CPU. |
| NLLB-200 CTranslate2 | Translation | Low-latency default; CPU or CUDA when the game reserve allows. |
| Qwen3 1.7B INT8 | Translation | Optional CPU/CUDA language model; slower than NLLB. |
| Hy-MT2 1.8B | Translation | Optional CPU translator; better wording on a small test, slower than NLLB. |

Model downloads resume after interruptions, are checked before use, and can be deleted from **Settings → Models**. Hugging Face downloads fall back to HF-Mirror when the original connection fails.

### Services/API

Configure one or more OpenAI-compatible domains under **Settings → Services/API** or the first-run online section. Each domain has its own name, URL, key and model choices. **Fetch models** queries `/models`; **Connect** checks the endpoint. API keys are stored in plain text under your Windows profile, not uploaded anywhere except the service you configure.

Hearing and Translating are independent choices. Local mode keeps both steps on this PC. Translation stays within the selected service; there is no silent fallback to another provider.

## Files and privacy

- `%APPDATA%\VRChat-Translator\ui.json` — window, language, audio and model settings.
- `%APPDATA%\VRChat-Translator\models.json` — service URLs, keys, model choices and fetched model lists in plain text.
- `%LOCALAPPDATA%\VRChat-Translator\engine.log` — speech, language, translation and timing diagnostics.
- `%LOCALAPPDATA%\VRChat-Translator\local-model\` — downloaded local model files.

Speech and typed text are sent only to the service selected under **Settings → Models**. No provider key is sent to GitHub during update checks.

## Troubleshooting

- **No VRChat status:** start VRChat first and enable OSC in its Action Menu.
- **No subtitles:** check the speaker button and subtitle source, then the voice detector setting.
- **No translation:** open `engine.log`; check the selected service, URL/key and model names. Use **Connect** or **Fetch models** in Settings.
- **Music is silent:** see [Music setup](MUSIC_SETUP.md). Selected-app music requires Windows 11.
- **Update check cannot reach GitHub:** set `VRCT_UPDATE_API` to a compatible mirror; see the notes below.

Optional environment overrides:

| Variable | Effect |
|---|---|
| `VRCT_NO_UPDATE=1` | Skip the source updater used by `run_ui.bat`. |
| `VRCT_CPU_THREADS=2` | Use two local-inference threads instead of one. |
| `VRCT_LOCAL_DEVICE=cpu` | Keep local translation on the CPU. |
| `VRCT_PROCESS_PRIORITY=normal` | Do not lower the process priority while gaming. |
| `VRCT_UPDATE_API=url` | Add a GitHub-release mirror; `{source}` is replaced with the repository. |
| `VRCT_VR_DIAGNOSTICS=1` | Add VR timing/input-loss summaries to `engine.log`. |

## Build from source

### Prerequisites

- Windows 10 1809+ / Windows 11 x64.
- [Python 3.12](https://www.python.org/) and [uv](https://docs.astral.sh/uv/).
- PowerShell 5.1 or newer (PowerShell 7 also works).
- Optional native mixer: Visual Studio 2022 C++/ATL and Windows SDK 10.0.26100. See [apo/README.md](apo/README.md).
- Optional AMD Whisper runtime: Vulkan SDK with `glslc`, CMake and Visual Studio 2022. See [tools/build-whisper-vulkan.ps1](tools/build-whisper-vulkan.ps1).

The release EXE bundles the Microsoft Visual C++ runtime DLLs; a separate system install script is not required.

### Set up the environment

```powershell
git clone https://github.com/SentoMinh/ART-Asia-realtime-Translator.git
cd ART-Asia-realtime-Translator

uv venv .venv-app --python 3.12
uv pip install --python .venv-app\Scripts\python.exe -r requirements.txt `
  --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
```

`requirements.txt` contains the runtime, local-model, test and packaging dependencies. The Windows CPU wheel for `llama-cpp-python` needs the extra index shown above.

### Run

```powershell
.venv-app\Scripts\python.exe -m ui.main          # real capture
.venv-app\Scripts\python.exe -m ui.main --demo   # example lines, no capture
```

`run_ui.bat` does the same and checks the source updater first; set `VRCT_NO_UPDATE=1` while developing.

### Tests

The automated test suite is kept in the **private development checkout** and is intentionally not published in the public repository. With that checkout:

```powershell
.venv-app\Scripts\python.exe -m pytest tests
.venv-app\Scripts\python.exe -m pytest tests/test_ui.py -q
```

Qt tests set `QT_QPA_PLATFORM=offscreen` themselves. Tests isolate `APPDATA`/`LOCALAPPDATA`, HTTP, audio and model runtimes; do not point them at real credentials or model caches.

### Build the release

The one-file build needs the native Whisper Vulkan DLL at `assets/whisper-vulkan/art_whisper_vulkan.dll` (or pass `-WhisperBuild <dir>`). The validated mixer DLL directory can be passed with `-MixerBuild`.

```powershell
powershell -File tools\build.ps1 -DistPath dist\1.1.0 `
  -MixerBuild .tools\apo-prototype-10

powershell -File tools\build.ps1 -Folder -DistPath dist\1.1.0 `
  -MixerBuild .tools\apo-prototype-10
```

The first command creates the one-file EXE; `-Folder` creates the extractable folder and a ZIP. Build outputs are copied to `dist\`.

Check the packaged program with isolated settings:

```powershell
$env:APPDATA = "$PWD\.tools\selfcheck\appdata"
$env:LOCALAPPDATA = "$PWD\.tools\selfcheck\localappdata"
.\dist\1.1.0\VRChat-Translator.exe --selfcheck
Get-Content "$env:LOCALAPPDATA\VRChat-Translator\selfcheck.txt"
```

### Release checklist

1. Bump `ui/__init__.py` and add a `CHANGELOG.md` entry.
2. Run the full test suite in the private checkout.
3. Build the EXE and folder ZIP; pass the validated native mixer directory.
4. Run the packaged `--selfcheck` with isolated AppData.
5. Generate `SHA256SUMS.txt` and update README/release notes.
6. Export committed source with `tools/export_public.py` into a **clean** public checkout. The export excludes `tests/`, `bench/`, `updates/` and the relay configuration.
7. Commit/tag `v<version>` in the public repository and upload the assets with GitHub Releases.

Never run `tools/export_public.py` against a populated checkout with local files you want to keep: it removes files that are not part of the committed export.

## Project layout

```text
ui/       PySide6 window, settings, first-run flow and the guided manual
engine/   voice detection, speech-to-text, translation and model downloads
vrc/      VRChat window discovery, OSC chatbox, audio capture
vr/       SteamVR wrist display and controller input
apo/      optional Windows microphone mixer
driver/   earlier virtual-microphone prototype (reference only)
tools/    build, preview, snapshot and release helpers
assets/   icons, VR hand data and native Whisper Vulkan runtime
tests/    automated tests (private development checkout only)
```

## Documentation

- [CHANGELOG.md](CHANGELOG.md) — behavior changes and validation notes.
- [CODEBASE.md](CODEBASE.md) — developer architecture map.
- [MUSIC_SETUP.md](MUSIC_SETUP.md) — music routing and compatibility.
- [LOCAL_TRANSLATION_PLAN.md](LOCAL_TRANSLATION_PLAN.md) — local model choices and checks.
- [LATENCY_REPORT.md](LATENCY_REPORT.md) — timing measurements and limits.
- [VR_OVERLAY_INVESTIGATION.md](VR_OVERLAY_INVESTIGATION.md) — SteamVR cursor/input findings.
- [ART Project Guide](ART%20Project%20Guide.md) — full project walkthrough.
