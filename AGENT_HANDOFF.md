# ART agent handoff — 23 October 2026

Read this first, then [CLAUDE.md](CLAUDE.md), [CODEBASE.md](CODEBASE.md), and the relevant entries in [CHANGELOG.md](CHANGELOG.md). This describes the current handoff; recheck Git and release state before making changes.

## Current state

| Item | State |
| --- | --- |
| Published app | **v0.12.5**, release source `11a5a1693d93dc07f01e4a6dce3ea8fdf488a37c` |
| Published EXE SHA-256 | `333d7acd2c73173801614e04be73881183e2ff3396261787a24fb55c2fd4967d` |
| Release validation | 505 tests; packaged self-check and real PhoWhisper/Qwen inference; native DLLs, model manifest, source/asset checks; actual GitHub upgrade 0.12.4 → 0.12.5 and up-to-date check passed |
| Earlier measurement commit | `2ad5087` in the release repository: [LATENCY_REPORT.md](LATENCY_REPORT.md); no binary change |
| Current release features | PhoWhisper Small, Qwen3 1.7B INT8, descriptive model cards and HF-Mirror fallback are included in 0.12.5. |
| Version constant | 0.12.5; preserve the existing 0.12.4 artifacts/tag |
| Model list | Whisper turbo, SenseVoice, PhoWhisper Small (VI CPU), NLLB and Qwen3 1.7B INT8 (CPU); non-turbo large-v3 removed |

The latest user request explicitly authorizes the model additions/removal and language/strength descriptions. Source tests: **505 passed**. Real pinned new weights loaded and ran; see LOCAL_TRANSLATION_PLAN.md and LATENCY_REPORT.md. Release evidence is under `.tools/release-0.12.5/`: `verification.json`, `packaged-inference.json`, `github-draft.json` and `live-update-result.json`. The final package includes production native DLLs and both new adapters. Real GitHub download, SHA-256 verification, packaged replacement/restart and new-version self-check passed. All five uploaded assets matched local digests. This documentation follow-up does not rebuild the tagged EXE.

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
- Update `ui/__init__.py`, translated update-notice strings, README/changelog and package notes for the next binary. Version 0.12.5 is allocated to these model changes; use a new version for subsequent binaries.
- The optional verified NLLB offline ZIP remains an asset of v0.12.3. Keep existing links valid, but it is not the user's preferred solution for this current request.

Run focused tests with `.venv-app\Scripts\python.exe -m pytest tests/test_local_model.py tests/test_local_choices.py tests/test_nllb_offline.py -q`; run the full suite before packaging. A source test result does not validate a new EXE or mainland-China access.
