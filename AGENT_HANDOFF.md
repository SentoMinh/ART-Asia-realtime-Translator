# ART agent handoff — 25 October 2026

**0.12.10 published:** added a separate `whisper-turbo-vulkan` hearing option for AMD-compatible Vulkan GPUs. See `native/whisper_vulkan/README.md` for pinned native build, model, ABI and validation details. The earlier NVIDIA/CPU choices and user settings are preserved. 536 tests and real Vulkan EN/ZH/VI inference on RTX 3080 passed. AMD hardware remains unverified; do not claim an AMD speed/accuracy result. Release/package verification passed; see the evidence below.

Read this first, then [CLAUDE.md](CLAUDE.md), [CODEBASE.md](CODEBASE.md), and the relevant entries in [CHANGELOG.md](CHANGELOG.md). This describes the current handoff; recheck Git and release state before making changes.

**0.12.9 source update:** the automatic translation add-on loader is removed for every service. The 0.12.7 fix covered local mode only; custom domains could still fall through to an old Gemini add-on. ServiceChain now uses only explicitly selected service/models. Existing add-on files remain on disk but are ignored. Switch prompts display custom-domain names. Preserve the separate Hearing/Translating selections; do not silently change providers. Full suite: 528 tests passed.

## Current state

| Item | State |
| --- | --- |
| Published app | **v0.12.10**, release source `f38139ac77baff5e0d44d559519992970778cc29` |
| Published EXE SHA-256 | `bd7e681dc074244783cd519da9a8701a7b267a7504c8eae465eac03e23d2c86e` |
| Release validation | 536 tests; actual EXE Vulkan load/warmup/no-GPU checks; package/source/native DLL/asset checks; GitHub upgrade 0.12.9 → 0.12.10 and no-update check passed |
| Earlier measurement commit | `2ad5087` in the release repository: [LATENCY_REPORT.md](LATENCY_REPORT.md); no binary change |
| Current release features | Separate Whisper turbo Vulkan (AMD) option with pinned Q5 download; previous NVIDIA/CPU models and selected-service translation boundary preserved. |
| Version constant | 0.12.10; preserve earlier versions and use a new version for subsequent binaries |
| Model list | Whisper turbo (NVIDIA CUDA), Whisper turbo Vulkan (AMD), SenseVoice, PhoWhisper Small, NLLB and Qwen3 1.7B INT8 |

Published release source `f38139a` (development `c3143fd`) passed 536 tests, EXE/source/runtime/license checks, actual packaged Vulkan model load/warmup and a no-compatible-GPU failure without a crash. All five GitHub assets matched their local sizes/digests. The actual 0.12.9 → 0.12.10 GitHub upgrade passed download/SHA-256, replacement/restart, new-version self-check and no-update checks. Real Vulkan recognition was tested on RTX 3080, not AMD. User settings were preserved. Evidence: `.tools/release-0.12.10/` and `.tools/whisper-vulkan/`.

The 0.12.9 fix is `a7b09a6` in the release repository (`4d8b164` in development). Evidence: `.tools/release-0.12.9/verification.json`, `packaged-boundary.json`, `github-draft.json` and `live-update-result.json`. Bundled translator bytecode was exercised with fake adapters for both local models and online services; actual EXE self-check separately verified that a legacy add-on trap was never imported. All five uploaded assets matched local digests. The user's provider/model choices and legacy files were preserved. A selected speech-generation model cannot translate text; ask before changing the user's provider/model. Live successful inference against the user's custom endpoint was not tested.

The 0.12.8 source is `6b3f9c3` in the release repository (`f9592e7` in development; detector fix `2e2a230`). Evidence: `.tools/release-0.12.8/verification.json`, `packaged-detector.json`, `github-draft.json`, `live-update-result.json` and `.tools/vad-0.12.8/final-replay.json`. The packaged detector and defaults controls passed with isolated settings; all five uploaded assets matched local digests. User microphone strictness was 71% during diagnosis and was preserved; direct the user to Restore detector defaults to compare with 50%. No live audio recording or recognition-accuracy benchmark was performed.

The 0.12.7 fix is source commit `f06758e` in the release repository (`ad4891a` in the development checkout). Evidence: `.tools/release-0.12.7/verification.json`, `packaged-routing.json`, `github-draft.json` and `live-update-result.json`. All five GitHub assets matched their local SHA-256 digests before publication. Isolated packaged checks used fake local translators and an add-on to verify failures never fall through while Local Model is selected; user settings/model files were untouched. Live VRChat audio and the original NLLB failure were not reproduced; this release fixes routing and error visibility, not inference accuracy.

The first update probe immediately after 0.12.7 publication returned no update. A subsequent anonymous API/asset probe returned the correct tag and HTTP 200; repeating the unchanged updater check passed. The initial empty result's exact cause was not captured. This documentation follow-up does not rebuild the tagged EXE.

The preceding 0.12.5 work added the models and descriptions with **505 tests passed**. Real pinned new weights loaded and ran; see LOCAL_TRANSLATION_PLAN.md and LATENCY_REPORT.md. Release evidence is under `.tools/release-0.12.5/`: `verification.json`, `packaged-inference.json`, `github-draft.json` and `live-update-result.json`. The final package includes production native DLLs and both new adapters. Real GitHub download, SHA-256 verification, packaged replacement/restart and new-version self-check passed. All five uploaded assets matched local digests.

## User decisions and open choices

- ART is one application. Do not introduce separate friend/public/private editions. Use Custom domain for different API endpoints.
- Prioritize voice recognition reliability and **low latency with preserved meaning**. Speaker identification is deferred; mention the saved idea during future feature planning, not as an implemented feature or scheduled reminder.
- The user prefers a normal online model download for their friend in China, not an offline-package workflow. They explicitly requested keeping Hugging Face and using `https://hf-mirror.com/` if the first source cannot connect.
- “Keep both” was interpreted as keeping both download sources. An unanswered clarification asked whether they also want **Hy-MT2 alongside NLLB**. Do not claim the second model was approved, installed or benchmarked.
- The latest request confirms removing non-turbo Whisper large-v3 and adding PhoWhisper plus a light Qwen. Removed selections fall back to turbo, but existing large-v3 weights are preserved. PhoWhisper is Vietnamese-focused; Qwen3 1.7B is optional. The tested 0.6B conversion failed basic translation checks and is not offered.
- Earlier requests authorized commits and release work; honor any newer scope changes. Ask before additional model-list changes or changing the user's selected providers. The Hugging Face → HF-Mirror fallback itself is authorized; do not request permission for it again.
- Use the user's installed Ponytail skill at full level for coding. Keep changes small and complete, and state verification limits. Temporary UI previews must close automatically or be closed when the check ends.

## New fallback: implementation and limits

`engine/local_model.py::_fetch` keeps the original pinned HTTPS URL and revision. For URLs beginning exactly with `https://huggingface.co/`, an initial network interruption, short response or refused HTTP response switches to the same path on `https://hf-mirror.com/`. It switches immediately rather than exhausting all original-host retries first. Existing partial bytes are resumed with Range; a server that returns 200 restarts the file. Mirror connection retries remain bounded by the existing `TRIES` limit. Non-Hugging-Face assets, including PyPI-hosted NVIDIA libraries, keep their existing source.

The original file size and SHA-256 are still required before installation. Corrupt files are discarded; oversized responses stop instead of looping. Cancellation and file-open/write errors stop without switching hosts. Switching is logged to the existing `engine.local_model` logger. There is no new settings toggle or download-provider dropdown.

Tests in `tests/test_local_model.py` cover healthy-primary behavior, network/HTTP failure, partial resume, ignored Range, corrupt mirror content, both sources failing, bounded retries, cancellation, disk failure and oversized responses. The focused downloader/local-choice/offline-installer run passed **39 tests**; the full suite passed **490 tests** after the fallback change.

A real small-file probe fetched the pinned NLLB `config.json` (1,065 bytes) and verified its SHA-256 after simulating failure of the initial primary request. **The real redirect chain was HF-Mirror 308 → Hugging Face 307 → Hugging Face 200.** This verifies the fallback code and returned bytes on this connection; it does not demonstrate independence from Hugging Face. Mainland-China connectivity and a full model-weight download through the mirror remain unverified. Do not promise that this fallback alone fixes the friend's connection.

Local evidence: `.tools/hf-mirror-probe/result.json`, `.tools/hf-mirror-tests.txt`. These are ignored development artifacts, not bundled app files.

## Important current behavior to preserve

- **I speak / They speak:** up to three recognition languages; They speak also offers Auto. Selecting multiple languages still involves detection followed by filtering. Hints are model-dependent: SenseVoice runs Auto internally; Chinese Whisper routing intentionally checks Mandarin/Cantonese before forcing a language.
- **Translated to:** up to three panel destinations only.
- **Chatbox languages:** follows all They speak choices by default, or up to three custom choices in Settings → Translation. Auto-detect resolves to the last heard language, falling back to English. Explicit typed Send overrides only typed destinations.
- Targets are captured on each `Utterance`. Translate the ordered union of panel/chatbox targets once; reuse original text for the source language. Preserve successful results when another target fails.
- Microphone chatbox messages contain the original plus selected translations in one message. `fit_lines` deduplicates and shares the 144-character budget. Preserve the existing OSC minimum gap and ordered microphone queue. Partial panel updates must never send partial chatbox messages.
- Local NLLB splits punctuated sentences, translates them in one batch, and retries excessive repetition once. Keep the earlier missing-sentence and repetition regression tests.
- Keep embedded setup/download panels, one model-list scrollbar, corner resize grip, text selection/copy, the below-30% click-through backdrop fix, and the once-per-version update notice.

## Latency evidence and next improvement opportunities

Read [LATENCY_REPORT.md](LATENCY_REPORT.md) before describing speed. With VRChat **closed**, warm medians were NLLB Modal **561 ms** vs local **299 ms**; three outputs **1,477 ms** vs **635 ms**; shared EN/ZH Auto hearing Modal SenseVoice **1,160 ms** vs local Whisper turbo **311 ms**. Different hearing models and unknown remote hardware prevent attributing the difference solely to networking.

Modal's first translation took 26.3 seconds, but cold start was not confirmed from server logs. Modal also omitted part of two multi-sentence inputs in all three repeats; local output retained both sentences. An HTTP-success result is not necessarily a quality success. Investigate that remote path before recommending it as a replacement for local translation, and obtain approval before changing a hosted service.

The earlier progressive-display change improved the first visible result, not inference duration: a controlled three-target test moved first display from 361 to 120 ms while total completion stayed around 361 ms. Local model reuse and Whisper warm-up already existed. The 0.8-second silence threshold remains intentional; do not lower it casually because 0.55 seconds previously cut speakers at breaths.

Next useful measurements are actual game/GPU contention, short conversational and noisy speech, complete multi-language delivery, and quality alongside timing. Qwen3 1.7B is now implemented as an alternative; Hy-MT remains a candidate. Neither is a proven speed improvement over NLLB. See [LOCAL_TRANSLATION_PLAN.md](LOCAL_TRANSLATION_PLAN.md).

## Workspace, commits and release procedure

- Development checkout: `F:\Code\vrchat-translator_9.10_gemini`, branch `music-mix`; Python `.venv-app\Scripts\python.exe`.
- Release checkout: `F:\Code\vrchat-translator-public`, branch `main`; GitHub `SentoMinh/ART-Asia-realtime-Translator`. Keep its Git history separate from the development repository.
- Check both working trees before editing/exporting. Use `tools.export_public.public_files()` and `problems()` on committed source. Copy verified files, check tracked destination files for obsolete paths, and compare normalized bytes. **Do not run the export script's main function against a populated checkout:** it recursively removes destination files outside the export, including ignored artifacts.
- Never bundle AppData settings, API credentials, logs, benchmark recordings, model weights or local infrastructure. Tests isolate AppData through `tests/conftest.py`; direct benchmarks must avoid saving provider changes or opening capture/OSC.
- For a new release, stage the committed/scanned source in a new `.tools/release-<version>/source` directory. Build with `tools/build.ps1`, the development Python, and validated `.tools/apo-prototype-10` DLLs. Preserve old artifacts. Bundle only `VrctMicApo.dll` and `VrctApoProducer.dll`, never test DLLs.
- Prior release helpers/evidence are in `.tools/release-0.12.4/`; adapt versions, source commit, notice assertions and test counts rather than copying old expectations blindly. Keep checksums, ZIP, packaged self-check, draft-asset verification, and the GitHub download/replacement/restart check.
- Update `ui/__init__.py`, translated update-notice strings, README/changelog and package notes for the next binary. Version 0.12.6 is published; use a new version for subsequent binaries.
- The optional verified NLLB offline ZIP remains an asset of v0.12.3. Keep existing links valid, but it is not the user's preferred solution for this current request.

Run focused tests with `.venv-app\Scripts\python.exe -m pytest tests/test_local_model.py tests/test_local_choices.py tests/test_nllb_offline.py -q`; run the full suite before packaging. A source test result does not validate a new EXE or mainland-China access.


## 0.12.6 release evidence

The latest requests added model deletion and an Obsidian-ready project-structure note. Published source is `ce06fb9`; the documentation follow-up does not rebuild that binary. All 518 tests passed. Native Windows previews verified inline confirmation/cancel and the legacy cleanup card, then closed automatically. The EXE self-check and an isolated packaged UI deletion probe passed, including cancellation, model and partial deletion, retired cleanup and preservation of other model/shared files. No real user model was deleted during validation.

Evidence: `.tools/release-0.12.6/verification.json`, `packaged-delete.json`, `github-draft.json` and `live-update-result.json`. The ZIP includes `ART Project Guide.md`; all five uploaded release assets matched local sizes/digests. Actual GitHub download, SHA-256 verification, packaged replacement/restart from 0.12.5, new-version self-check and no-update check passed. The new deletion behavior does not remove external caches or unload already-resident weights. Windows file locks, other running ART instances and fresh-PC installation remain practical limits.
