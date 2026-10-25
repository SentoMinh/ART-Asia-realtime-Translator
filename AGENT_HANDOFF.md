# ART agent handoff — 25 October 2026

**0.12.13 scope correction published:** the user answered “Only the latency and translation fixes” after 0.12.12 had already been published. Restore the 0.12.11 Sound reset card and compact guide; retain all latency/translation fixes. The expanded guide is preserved at `.tools/scope-0.12.13/ART Project Guide - expanded.md` and must not be included again without a new request. Do not rewrite the published 0.12.12 assets. Package and actual GitHub upgrade checks passed.

**0.12.12 published:** mixed CJK text labelled EN/VI now reaches the selected translator and remains visible; ordinary same-language original reuse stays fast. Installed local translation weights preload on the existing worker with retryable failures. Sound reset card removed; detector settings are unchanged. Expanded Obsidian guide included. 559 source tests passed; local text replay and rendering evidence: `.tools/local-translation-diagnosis/`. NLLB still changes meaning on a repeated Chinese example. Package and actual GitHub upgrade checks passed.

**0.12.11 published:** online target requests now overlap, at most two per utterance, with completion-order partial results and panel-first scheduling. Local inference remains serialized. HTTP client/chain creation and cooldown bookkeeping are synchronized. New timing logs separate recognition from translation. Five warm paired phrases measured two-target median 188.8 → 102.8 ms through the configured online service, not end-to-end/FPS or local performance. See LATENCY_REPORT.md and `.tools/latency-0.12.11/`. Preserve prompts, model selections, VAD/decoding and complete ordered chatbox sends. Release and actual GitHub upgrade checks passed; see the evidence below.

**0.12.10 published:** added a separate `whisper-turbo-vulkan` hearing option for AMD-compatible Vulkan GPUs. See `native/whisper_vulkan/README.md` for pinned native build, model, ABI and validation details. The earlier NVIDIA/CPU choices and user settings are preserved. 536 tests and real Vulkan EN/ZH/VI inference on RTX 3080 passed. AMD hardware remains unverified; do not claim an AMD speed/accuracy result. Release/package verification passed; see the evidence below.

Read this first, then [CLAUDE.md](CLAUDE.md), [CODEBASE.md](CODEBASE.md), and the relevant entries in [CHANGELOG.md](CHANGELOG.md). This describes the current handoff; recheck Git and release state before making changes.

**0.12.9 source update:** the automatic translation add-on loader is removed for every service. The 0.12.7 fix covered local mode only; custom domains could still fall through to an old Gemini add-on. ServiceChain now uses only explicitly selected service/models. Existing add-on files remain on disk but are ignored. Switch prompts display custom-domain names. Preserve the separate Hearing/Translating selections; do not silently change providers. Full suite: 528 tests passed.

## Current state

| Item | State |
| --- | --- |
| Published app | **v0.12.13**, release source `2a5d0a0cd2afeffb90ffe436d44bd5893f3e2092` |
| Published EXE SHA-256 | `ba96c2df16c959ba6d7a895c0c3fc95e9d92cf5af554fdc47835731687948348` |
| Release validation | 560 tests; 323 bundled checks; EXE/native/source/asset checks; actual GitHub upgrade 0.12.12 → 0.12.13 passed |
| Earlier measurement commit | `2ad5087` in the release repository: [LATENCY_REPORT.md](LATENCY_REPORT.md); no binary change |
| Current release features | Latency and translation fixes retained; earlier Sound reset card and compact guide restored. Expanded guide excluded from the release. |
| Version constant | 0.12.13; preserve earlier versions and use a new version for subsequent binaries |
| Model list | Whisper turbo (NVIDIA CUDA), Whisper turbo Vulkan (AMD), SenseVoice, PhoWhisper Small, NLLB and Qwen3 1.7B INT8 |

Published release source `2a5d0a0` (development `f5fcd94`) passed 560 source tests and 323 checks against bundled translation/local-model/UI bytecode, including the restored detector reset control. Actual EXE self-check, source/native/runtime checks, ZIP integrity and all five GitHub asset digests passed. The real 0.12.12 → 0.12.13 upgrade passed download/SHA-256, packaged replacement/restart, new-version self-check and no-update checks. Saved settings were unchanged. Latency/translation implementation is unchanged from 0.12.12; the reset card matches 0.12.11. The compact guide is bundled; the expanded guide is preserved locally outside the release. Live audio and game performance were not retested. Evidence: `.tools/release-0.12.13/` and `.tools/scope-0.12.13/`.

Published release source `2df0d65` (implementation `5ee86df`; development `fbdc497`, documentation `95630d5`) passed 559 source tests, 170 subsequent focused checks and 322 checks against bundled translation/local-model/UI bytecode. Actual EXE self-check, source/native/runtime checks, ZIP integrity and all five GitHub asset digests passed. The real 0.12.11 → 0.12.12 upgrade passed download/SHA-256, packaged replacement/restart, new-version self-check and no-update checks. User settings were unchanged. The local mixed-text replay is a text/model/rendering check, not a live recognition or game-FPS test. NLLB still changes meaning on a repeated Chinese example. Evidence: `.tools/release-0.12.12/` and `.tools/local-translation-diagnosis/`.

Published release source `a03ab48` (development `8d3b8f8`) passed 544 tests and 43 checks against bundled translation bytecode for concurrent targets, partial results, cooldowns, local isolation and ordered chatbox messages. The actual EXE self-check, bundled native DLL hashes, source/asset scans and ZIP checks passed. All five uploaded GitHub assets matched local sizes/digests. The real 0.12.10 → 0.12.11 upgrade passed download/SHA-256, packaged replacement/restart, new-version self-check and no-update checks. User settings were unchanged. Live recognition errors, game FPS and end-to-end speech latency were not tested. Evidence: `.tools/release-0.12.11/`.

Published release source `f38139a` (development `c3143fd`) passed 536 tests, EXE/source/runtime/license checks, actual packaged Vulkan model load/warmup and a no-compatible-GPU failure without a crash. All five GitHub assets matched their local sizes/digests. The actual 0.12.9 → 0.12.10 GitHub upgrade passed download/SHA-256, replacement/restart, new-version self-check and no-update checks. Real Vulkan recognition was tested on RTX 3080, not AMD. User settings were preserved. Evidence: `.tools/release-0.12.10/` and `.tools/whisper-vulkan/`.

The 0.12.9 fix is `a7b09a6` in the release repository (`4d8b164` in development). Evidence: `.tools/release-0.12.9/verification.json`, `packaged-boundary.json`, `github-draft.json` and `live-update-result.json`. Bundled translator bytecode was exercised with fake adapters for both local models and online services; actual EXE self-check separately verified that a legacy add-on trap was never imported. All five uploaded assets matched local digests. The user's provider/model choices and legacy files were preserved. A selected speech-generation model cannot translate text; ask before changing the user's provider/model. Live successful inference against the user's custom endpoint was not tested.

The 0.12.8 source is `6b3f9c3` in the release repository (`f9592e7` in development; detector fix `2e2a230`). Evidence: `.tools/release-0.12.8/verification.json`, `packaged-detector.json`, `github-draft.json`, `live-update-result.json` and `.tools/vad-0.12.8/final-replay.json`. The packaged detector and defaults controls passed with isolated settings; all five uploaded assets matched local digests. User microphone strictness was 71% during diagnosis and was preserved; in 0.12.12, use the Sound slider to compare with 50% because the reset card has been removed. No live audio recording or recognition-accuracy benchmark was performed.

The 0.12.7 fix is source commit `f06758e` in the release repository (`ad4891a` in the development checkout). Evidence: `.tools/release-0.12.7/verification.json`, `packaged-routing.json`, `github-draft.json` and `live-update-result.json`. All five GitHub assets matched their local SHA-256 digests before publication. Isolated packaged checks used fake local translators and an add-on to verify failures never fall through while Local Model is selected; user settings/model files were untouched. Live VRChat audio and the original NLLB failure were not reproduced; this release fixes routing and error visibility, not inference accuracy.

The first update probe immediately after 0.12.7 publication returned no update. A subsequent anonymous API/asset probe returned the correct tag and HTTP 200; repeating the unchanged updater check passed. The initial empty result's exact cause was not captured. This documentation follow-up does not rebuild the tagged EXE.

The preceding 0.12.5 work added the models and descriptions with **505 tests passed**. Real pinned new weights loaded and ran; see LOCAL_TRANSLATION_PLAN.md and LATENCY_REPORT.md. Release evidence is under `.tools/release-0.12.5/`: `verification.json`, `packaged-inference.json`, `github-draft.json` and `live-update-result.json`. The final package includes production native DLLs and both new adapters. Real GitHub download, SHA-256 verification, packaged replacement/restart and new-version self-check passed. All five uploaded assets matched local digests.

## User decisions and open choices

- The latest explicit release scope is **only latency and translation fixes**. Exclude the other terminal's Sound-page cleanup and expanded Obsidian guide. Version 0.12.13 restores the previous reset card and compact guide while keeping the performance and mixed-text fixes.
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
- Targets are captured on each `Utterance`. Translate the ordered union of panel/chatbox targets once; reuse original text for the source language unless the EN/VI output contains CJK text. Preserve successful results when another target fails.
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
- Update `ui/__init__.py`, translated update-notice strings, README/changelog and package notes for the next binary. Version 0.12.13 is published; use a new version for subsequent binaries.
- The optional verified NLLB offline ZIP remains an asset of v0.12.3. Keep existing links valid, but it is not the user's preferred solution for this current request.

Run focused tests with `.venv-app\Scripts\python.exe -m pytest tests/test_local_model.py tests/test_local_choices.py tests/test_nllb_offline.py -q`; run the full suite before packaging. A source test result does not validate a new EXE or mainland-China access.


## 0.12.6 release evidence

The latest requests added model deletion and an Obsidian-ready project-structure note. Published source is `ce06fb9`; the documentation follow-up does not rebuild that binary. All 518 tests passed. Native Windows previews verified inline confirmation/cancel and the legacy cleanup card, then closed automatically. The EXE self-check and an isolated packaged UI deletion probe passed, including cancellation, model and partial deletion, retired cleanup and preservation of other model/shared files. No real user model was deleted during validation.

Evidence: `.tools/release-0.12.6/verification.json`, `packaged-delete.json`, `github-draft.json` and `live-update-result.json`. The ZIP includes `ART Project Guide.md`; all five uploaded release assets matched local sizes/digests. Actual GitHub download, SHA-256 verification, packaged replacement/restart from 0.12.5, new-version self-check and no-update check passed. The new deletion behavior does not remove external caches or unload already-resident weights. Windows file locks, other running ART instances and fresh-PC installation remain practical limits.
