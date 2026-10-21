# Project context

Read `CODEBASE.md` for the architecture, export status, test baseline and remaining review items. It describes source version 0.12.2 and the preceding release validation; recheck current code before relying on its findings.

Read `CHANGELOG.md` for the reason behind recent changes, their implementation commits, regression tests and troubleshooting steps.

## Scope and existing work

- Read `ROADMAP.md` when planning features: voice recognition is the current priority. Speaker 1 / Speaker 2 identification is deferred; remind the user when discussing future work. Close temporary demo previews after verification.

- This is a Windows VRChat desktop translator written in Python 3.12 with PySide6.
- Build on the existing implementation. Locate the relevant module and tests before adding a new abstraction or feature.
- `F:\Code\vrchat-translator` is a sibling reference copy. Compare it before porting work; do not synchronize folders automatically.
- Check both working trees before synchronizing; earlier onboarding found uncommitted local-model changes. Preserve unrelated edits and untracked work.
- Both copies share AppData settings, provider keys, logs and the local-model cache. Use temporary paths/fakes for checks that change state.
- Version 0.11.10 has one app and one build. Its EXE/ZIP are published on GitHub, with the built source identified by its release tag. Preserve artifacts under `dist/<version>/`; a source or documentation commit does not rebuild them.
- Follow the user’s current authorization for commits, builds and publication. Use a new version directory for a new binary; preserve prior artifacts. Clarify scope only when authorization is missing or unclear.
- Synchronize source through reviewed changes and privacy checks. Preserve unrelated local artifacts in destination checkouts.

## Architecture and conventions

- `app.py`: packaged entry point and self-check; `ui/main.py`: GUI startup.
- `ui/backend.py`: `Backend`, `Status`, `Utterance` contracts. Re-emit the same utterance ID to update an existing row.
- `ui/live_backend.py`: capture lifecycle, typed translation, chatbox queue and typing dots.
- `vrc/audio.py`, `vrc/chatbox.py`: Windows capture, OSC integration and visible VRChat-window discovery for the header positioning button.
- `engine/vad.py`, `engine/speech.py`: segmentation, recognition scheduling, translation and routing.
- `engine/stt.py`: cloud/local recognition through `load()` and `transcribe()` returning `Heard`.
- `engine/services.py`: service registry, configuration, request helpers and per-domain model catalogs bound to URL/key fingerprints.
- `ui/widgets.py`: `DialogPanel` embeds setup/download forms; preserve cancellation, navigation restoration and shared downloads. Keep the model list to one scroll area and one Close button.
- `ui/main_window.py`: below 30%, alpha-zero blank space passes clicks through; text/input/top controls stay interactive. `ui/overlay_backdrop.py` preserves the selected darkness on an input-transparent surface behind the text; keep its geometry, stacking and lifetime aligned with the overlay. Use the standard bottom-right `QSizeGrip` to resize; only the top edge/corners also accept native edge resizing. The embedded update notice uses `Settings.last_update_notice` and must have current release text.
- `ui/settings_window.py`: API setup with Fetch models; Connect beside each domain; visible model dropdown arrows below Hearing/Translating. Selections save immediately; manual model entry remains available.
- `ui/service_health.py`: silent startup/API checks, 30-second deadline, Settings status and stale-result handling. Do not reintroduce the startup popup.
- `engine/translators.py`, `vrc/translate.py`: provider adapters, add-ons, fallback chain and shared prompts.
- `engine/local_model.py`, `ui/local_download.py`: verified/resumable downloads and Qt progress signals.
- `ui/config.py`: shared settings and persistence; `ui/i18n.py`: English-keyed Chinese/Vietnamese translations.
- `ui/theme.py`, `ui/widgets.py`, `ui/log_view.py`: existing appearance and message controls.
- `ui/music_dialog.py`, `vrc/apo_player.py`, `apo_music.py`, `apo_transport.py`: selected-app audio into the physical microphone through the native APO.
- `vrc/apo_install.py`, `apo_setup.py`, `apo/`: bundled microphone setup, UAC consent, validation and rollback. `driver/` is an earlier unused kernel-driver prototype.
- Speech/text languages are English, Mandarin, Cantonese, Vietnamese, Japanese and Korean. Keep UI/recognition/translation language lists aligned. Interface languages remain English, Chinese and Vietnamese by user choice.
- Follow snake_case functions/files, PascalCase classes, type hints and dataclasses used nearby.
- Keep audio callbacks fast and queue work. Use Qt signals for GUI updates from workers.
- Preserve ordered microphone output, sentence priority, stale-line handling and chatbox pacing.
- Raise existing `SttError` / `TranslateError` types with useful messages so fallback and status handling keep working.
- Add UI strings through `tr()` and both existing translation tables.
- `bench/` contains separate evaluation adapters/results; production features belong in `engine/`, `ui/` or `vrc/`.

## Run and verify

- Tests: `.venv-app\Scripts\python.exe -m pytest tests`.
- Tests use pytest, fake clocks, fake HTTP/audio/model dependencies and Qt offscreen mode. Extend the nearest existing test file for meaningful behavior changes.
- Direct launch: `.venv-app\Scripts\python.exe -m ui.main`; demo: append `--demo`.
- `run_ui.bat` also invokes the source Git updater. `VRCT_NO_UPDATE=1` disables that check.
- Build: `pwsh -File tools\build.ps1 -MixerBuild .tools\apo-prototype-10`; use the validated native build path. Optional `-Folder`. Bundle only the explicit build assets; never bundle provider configuration or the test APO DLL.
- UI snapshots: `.venv-app\Scripts\python.exe tools\snapshot_ui.py <output-folder>`.
- Packaged check: `VRChat-Translator.exe --selfcheck`; it can probe devices/network. `--get-local-model` additionally permits a large model download.
- Unit-test success is separate from live VRChat, GPU, service and packaged-build validation.
- Version 0.11.10 passed 422 tests, packaged self-checks, runtime/native-DLL checks, source/artifact scans and ZIP/checksum checks. The GitHub download and packaged upgrade from 0.11.9 to 0.11.10 were verified. Live Windows 10 and fresh-machine mixer installation remain outstanding; selected-app music currently requires Windows 11.
- Provider credentials belong in the existing AppData configuration, not source files or test fixtures.
- Source updates and packaged updates live in `tools/update.py` and `ui/updater.py`. Releases belong in `SentoMinh/ART-Asia-realtime-Translator`.
