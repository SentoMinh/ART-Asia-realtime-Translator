# AGENTS.md

Windows-only VRChat desktop translator (Python 3.12, PySide6). Detailed history and conventions live in
[CLAUDE.md](CLAUDE.md); current release/validation state lives in [AGENT_HANDOFF.md](AGENT_HANDOFF.md).

## Commands

- Python for everything: `.venv-app\Scripts\python.exe`. `.venv` exists but has no PySide6 — do not use it.
- Full suite: `.venv-app\Scripts\python.exe -m pytest tests` (750 tests, ~50 s without network). There is no CI, lint,
  formatter, or typecheck config: pytest is the only gate, so don't invent extra steps.
- One test: `.venv-app\Scripts\python.exe -m pytest tests/test_engine.py::test_name -q`.
- Recreate the environment: `uv pip install --python .venv-app\Scripts\python.exe -r requirements.txt --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu`
  (the Windows CPU wheel of `llama-cpp-python` is not on PyPI).
- Launch source app: `.venv-app\Scripts\python.exe -m ui.main` (`--demo` for fake data). `app.py` is the packaged entry point.
- `run_ui.bat` runs the Git updater first; set `VRCT_NO_UPDATE=1` while testing. The updater only fast-forwards a
  clean `main`; work branches (currently `music-mix`) are skipped.
- Previews without hardware: `.venv-app\Scripts\python.exe tools\snapshot_ui.py <out>` (window/settings) and
  `snapshot_vr.py <out>` (wrist panel), both `--lang en|zh|vi`; `preview_wrist.py` renders the headset view,
  `preview_music.py` the mixer dialog, `check_vr_texture.py` the real OpenGL upload/readback path.
- Build: `pwsh -File tools\build.ps1` (one-file EXE) or `-Folder`; `-MixerBuild .tools\apo-prototype-10` for the validated
  mixer. It refuses without `assets/whisper-vulkan/art_whisper_vulkan.dll` and its license (`-WhisperBuild <dir>` points
  elsewhere). Version comes from `ui/__init__.py` (1.0.6).
- Packaged check: `VRChat-Translator.exe --selfcheck` writes `%LOCALAPPDATA%\VRChat-Translator\selfcheck.txt` (probes
  devices/network; `--get-local-model` first downloads ~2 GB).

## Layout and flow

- `ui/main.py` starts the GUI; `engine.attach(backend)` wires capture to the window. `engine/__init__.py` calls
  `configure_native_threads()` at import time, before any model loads, so import order matters for thread settings.
- `ui/backend.py` defines `Backend`/`Status`/`Utterance`; re-emit the same utterance ID to update a row.
  `ui/live_backend.py` owns capture lifecycle, translation and the chatbox queue.
- `engine/`: `vad.py` (detection), `speech.py` (bounded queues, mic priority, stale dropping), `stt.py` (cloud/local
  recognition), `local_inference.py` (translator singletons + shared lock + GPU/CPU budget), `translators.py`,
  `services.py` (provider registry/catalogs), `local_model.py` (verified resumable downloads).
- `vrc/`: Windows audio capture, OSC chatbox, VRChat window discovery. `vr/`: SteamVR wrist display.
- `apo/`, `driver/`: microphone mixer. `driver/` is an unused earlier kernel prototype.
- `bench/` is evaluation-only; production code belongs in `engine/`, `ui/`, or `vrc/`.

## Conventions that are easy to break

- Add every UI string via `tr()` and update **both** `_ZH` and `_VI` tables in `ui/i18n.py`; English keys are the source text.
- Preserve: microphone priority, ≤8 pending sentences, ≤4 in-flight translations per source, 10 s stale limit,
  144-character chatbox budget, no partial chatbox sends, ordered output.
- Keep audio callbacks fast (queue the work) and send GUI updates from workers through Qt signals.
- Raise existing `SttError` / `TranslateError` types so fallback and status handling keep working.
- Translation stays within the selected service. Do not restore automatic add-on fallback (removed in 0.12.9).
- Do not change saved models/providers without asking; speaker 1/2 identification is deferred.
- Current defaults: one inference thread, below-normal process priority, CUDA for NLLB/Qwen only with a 3 GiB reserve.
  Overrides: `VRCT_CPU_THREADS=2`, `VRCT_LOCAL_DEVICE=cpu`, `VRCT_PROCESS_PRIORITY=normal`. Preserve CPU fallback.
- Tests isolate `APPDATA`/`LOCALAPPDATA` and the services cache (`tests/conftest.py`); Qt tests set
  `QT_QPA_PLATFORM=offscreen` themselves. Never point tests at real AppData credentials or model caches.
- Tests fake clocks, HTTP, audio, and model runtimes. Extend the nearest existing test file instead of adding
  hardware- or network-dependent coverage.
- Real user state: settings `%APPDATA%\VRChat-Translator\ui.json`; models/logs `%LOCALAPPDATA%\VRChat-Translator\`.
- Unit tests passing does not imply live VRChat, GPU, service, or packaged-build validation.

## Release and destructive-command safety

- `tools/export_public.py` deletes files in the target checkout that are absent from this repo's HEAD. Never run it
  with `main()` against a populated public checkout; inspect `public_files()` / `problems()` first. It copies only
  committed work and refuses on secrets.
- 1.0.6 is a local build; **0.12.14 is the last published GitHub release** (`SentoMinh/ART-Asia-realtime-Translator`).
  Check tags/GitHub before claiming a release exists.
- Preserve `dist/<version>/` artifacts; source/docs commits do not rebuild them. A new binary needs a new version directory.
- Never bundle provider configuration or the test APO DLL.
- Sibling `F:\Code\vrchat-translator` is a reference copy, not a sync target. Both trees share AppData state.
- `.tools/`, `.venv*`, `dist/`, `build/` are ignored. `.obsidian/` is untracked user content — do not edit or commit it.

## Reference docs

Use `/agy` (`agy` CLI) in the terminal for external research; local code inspection and tests run directly.
Record research and optimization outcomes, including rejected approaches and testing limits, in the relevant report
and handoff. The research/evidence index is at the top of [LATENCY_REPORT.md](LATENCY_REPORT.md).

[AGENT_HANDOFF.md](AGENT_HANDOFF.md) newest-first release log — read the top before release work ·
[CODEBASE.md](CODEBASE.md) architecture map and source changes after 1.0.6 ·
[CHANGELOG.md](CHANGELOG.md) reasons/commits/limits · [LATENCY_REPORT.md](LATENCY_REPORT.md) measurements ·
[LOCAL_TRANSLATION_PLAN.md](LOCAL_TRANSLATION_PLAN.md) model choices · [VOICE_DETECTION.md](VOICE_DETECTION.md)
before touching detector thresholds · [README.md](README.md) user-facing behavior.
