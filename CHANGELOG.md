# Change log

## 1.0.7 — 2026-10-30 — Gaming budget, bounded speech, and an update check that explains itself

The first published build after **0.12.14**. It carries the gaming CPU/GPU budget and bounded-speech work written on 2026-10-27 (kept below, unchanged) plus the update-check changes in this section. Package: `dist/1.0.7/` — one-file EXE and folder ZIP.

### Update check

`ui/updater.py` now writes every failed step of the packaged update check to `engine.log` — no answer, a non-200 answer, an unreadable answer, a damaged download, an answer without a digest — instead of returning nothing. Previously a single empty result could mean "up to date", "rate limited", "GitHub blocked" or "asset not ready", which is exactly what `AGENT_HANDOFF.md` could not tell apart after 0.12.7. `VRCT_UPDATE_API` adds one or more mirror addresses, separated by commas or semicolons, with `{source}` replaced by the repository. GitHub is still asked first; a mirror only answers where GitHub is blocked (mainland China without a VPN). The download link is taken from whatever answer wins, so a mirror needs no code change beyond serving the same JSON as `/releases/latest`.

Two crash paths are fixed. A half-finished download is deleted when the transfer raises, instead of waiting on disk as `.part` until the next start truncates it. A `.old` copy that is still held open by a closing instance no longer blocks the pending update forever: the running program is backed up as `.old2` (then `.old3`…) and the older copies are cleared on the next start. This does not change the rule that only a complete, size- and digest-checked `.new` is ever swapped in.

Validation: **756 source tests passed** on the documented environment (Python 3.12.15, PySide6 6.11.2), with 6 new updater tests (mirror fallback, GitHub still first, `{source}` substitution, interrupted-download cleanup, held-open `.old`, leftover cleanup). The packaged `VRChat-Translator-1.0.7.exe` passed `--selfcheck` with every part reported working, including the music mixer and a live `api.github.com` answer (HTTP 200). Not verified: a real mirror, any mainland-China network, or an actual replace-and-relaunch upgrade from an older EXE. Separately, this checkout's `.venv-app` was copied from another PC and its `pyvenv.cfg` pointed at `C:\Users\Admin\...`, which does not exist here; it was repaired by installing CPython 3.12.15 under `.tools\python` and relinking the environment with `uv venv --allow-existing`.

## 2026-10-27 — Gaming CPU/GPU budget and bounded speech (shipped in 1.0.7)

Written after 1.0.6 (`1efb598`) and shipped in the 1.0.7 package above. It reduces contention with a running game and makes the speech path degrade predictably when recognition or translation falls behind.

### CPU and scheduling

Local inference uses **one thread by default** instead of two: Whisper's CPU side, PhoWhisper, SenseVoice, NLLB/Qwen and Hy-MT2 all read `engine.runtime.cpu_threads()`. `VRCT_CPU_THREADS=2` restores the previous two-thread behavior. Native pools now sleep between work (`OMP_WAIT_POLICY=PASSIVE`, `KMP_BLOCKTIME=0`, one OpenMP/MKL/OpenBLAS/NumExpr thread) and tokenizer parallelism is off, unless those variables were already set. On Windows the process starts below normal priority so game threads run first; `VRCT_PROCESS_PRIORITY=normal` opts out. This reintroduces a setting rejected during the 1.0.5 whole-app replay, which found lower translation throughput when the CPU was saturated. It is a gaming tradeoff, not a measured speed win, and was not re-benchmarked here.

### GPU translation with a game reserve

NLLB and Qwen can use CUDA `int8_float16` when exactly one unmapped CUDA device is visible, both cuBLAS 12 DLLs are present, the runtime supports that compute type, and free VRAM is at least the model estimate plus **3 GiB**. NLLB estimates 1.5 GiB and Qwen 3 GiB, including the CUDA context and decoding workspace. Otherwise the model stays on CPU. `VRCT_LOCAL_DEVICE=cpu` forces CPU.

Free VRAM is checked before loading, immediately after CUDA loading, then before inference and during idle polling at most once every 10 seconds. These checks cannot guarantee a continuous reserve during inference. A CUDA load failure, failed post-load reserve check or pre-inference memory-pressure check switches the current request to CPU. Idle pressure unloads GPU weights without allocating CPU weights until the next request. A CUDA/OOM inference failure reports a `TranslateError` for the current line and loads CPU on the next request; the failed line is not retried automatically. GPU failures/pressure pin that model to CPU until another local model is loaded or the app restarts, avoiding repeated CUDA attempts.

Switching Translating away from Local Model releases its weights, cache and threads on the translate worker; when online hearing recovers after a local fallback, the fallback recognizer is released on the hearing thread. Queued releases recheck the current provider, with the translation check under the shared model lock, so reselecting Local Model before cleanup preserves its weights.

### Bounded speech and honest completion

Capture callbacks never wait for recognition. The audio queue holds at most 128 chunks and drops audio older than 2 seconds, resetting only that source's detector and resampler. Pending sentences are capped at 8, keeping microphone priority and discarding the oldest speaker sentence first. At most 4 translations per source may run or wait. Stale microphone speech is now dropped like speaker speech and cancels the typing dots instead of producing a late chatbox message. When capacity is exhausted, a stale line expires or shutdown arrives, the row is finalized with a localized note and is never sent. Saved settings are applied before speech attachment, so startup respects the selected hearing provider and capture switches. If both the microphone and subtitles are off at startup, the hearing model is not loaded; the first use loads it.

### Display and Settings

The wrist display ticks once a second while disabled or SteamVR is absent, instead of every 50 ms. While look-only hides the wrist, text and appearance changes wait; revealing draws the latest state immediately instead of waiting for the normal debounce. Settings stops its model-label refresh timer while hidden and refreshes on show. NLLB/Qwen model cards now say **GPU / CPU**. The CUDA DLL search path is kept alive without duplicating PATH entries.

### Validation

All **750 source tests passed** (734 before the final regression tests), including fake CUDA runtimes/OOM, VRAM pressure, startup settings, provider-reselection races, queue overload, shutdown, stale audio, online-hearing fallback and wrist idle rendering. An isolated offscreen startup/shutdown passed with `OMP_NUM_THREADS=1` and `KMP_BLOCKTIME=0`. Real installed NLLB/Qwen lifecycle checks matched CPU/CUDA output for one English-to-Vietnamese sentence, unloaded under injected low-memory telemetry, and returned to CPU. The observed free-VRAM decrease was about 1.1 GiB for NLLB and 2.2 GiB for Qwen; this is not isolated process-memory accounting or a real game-pressure test.

One pass over three synthetic lines after loading and an excluded warm-up took NLLB GPU 0.21 s, CPU one thread 1.74 s, CPU two threads 1.06 s (summed wall time); Hy-MT2 took one thread 4.55 s, two threads 2.50 s. These totals exclude model loading and are not per-line averages. Lifecycle timings include loading and are not comparable warm speed measurements. Evidence: `.tools/gaming-validation/`, `.tools/gaming-cpu1.json`, `.tools/gaming-cpu2.json` and `.tools/gaming-gpu.json`; [LATENCY_REPORT.md](LATENCY_REPORT.md) separates load, warm wall time and CPU time. These are component checks, not end-to-end latency, game FPS, live VRChat, headset or Windows 10 checks. The priority tradeoff was not re-measured.

## 1.0.6 — 2026-10-26 — Compact local model list

Local model cards are grouped under Hearing and Translating section headings, with spacing between categories and one shared scrollbar. Native previews verified both groups in English, Chinese and Vietnamese; all 116 UI tests passed.

Removed the model picker's introduction and model explanations. Cards show `Hearing/Translating - model name - GPU/CPU`, supported languages and download status. Download/stop, use and delete/cancel actions use compact icons with translated tooltips and accessible names. Inline delete confirmation remains. Translation model display names omit runtime/vendor suffixes; model IDs and saved selections are unchanged.

Follow-up: removed the duplicate introduction from the parent Models settings card too, including its unused translation entries and empty description space. All 116 UI tests passed; the actual Models page and embedded picker were previewed in all three interface languages.

All 146 focused UI/model tests passed before release preparation. Native Windows previews passed 27 combinations of interface language, width and display scaling, including delete confirmation previews, and closed automatically. Evidence: `.tools/model-list-ui/`. Version 1.0.6 is exported as a new local package with updated English/Chinese/Vietnamese release notices; existing 1.0.5 artifacts are preserved. Release verification is recorded in `.tools/release-1.0.6/`.

## 1.0.5 — 2026-10-26 — Hy-MT2 translation and lower CPU use

Today's combined local release includes the SteamVR wrist integration and responsive main window from 0.12.14, the CPU improvements below, and the existing local speech/translation fixes. The English, Chinese and Vietnamese update notices describe this version. GitHub publication is separate; 0.12.14 remains the published package.

Settings → Models can download Tencent Hy-MT2 1.8B (Q4_K_M, llama.cpp, CPU only) as a translation choice. On 31 local sentences it kept meaning better than the existing Qwen3 1.7B and than Qwen2.5 3B, which also left Chinese untranslated, so Qwen2.5 is not offered. It takes about three times longer than NLLB and more CPU, so NLLB remains the default and the saved selection was not changed. The verified file is already in the local model cache.

### Local translation reliability

Punctuation-only recognition is discarded before translation or chatbox output. Local translators return punctuation-only typed text unchanged. NLLB/Qwen inference failures can retry on the next sentence instead of blocking the model for a long cooldown. Qwen uses a shorter translation-only prompt and rejects common reasoning preambles; existing completed-output, repetition and script checks remain.

### Lower background CPU

The user reported PC lag whenever ART is open with local SenseVoice + Qwen and the voice detector off. A whole-app replay measured Qwen as about 94% of ART's CPU; details and limits are in LATENCY_REPORT.md (26 October).

- Local Qwen passes the target-language instructions as CTranslate2's cached static prompt when they are an exact token prefix; otherwise the whole prompt is sent as before. Output was byte-identical in 45 real calls; CPU per call fell 8.6% (20% for short lines).
- The local translation chain remembers the last 256 lines per target/source/heard flag. Greedy local decoding repeats its answer, so repeated lines such as "T." skip the model. Errors are not remembered; cooldowns and chain names are unchanged.
- The Music dialog stops its 50 ms poll when hidden with no music or check running, and checks VRChat's microphone only while shown. The log reader keeps its byte position and scans only appended lines: 61.9 → 0.21 ms per check on an 8 MB log. A new session or truncated log is read again from the last 8 MB.
- Level bars repaint only when the drawn line changes; the repeated 2-second VRChat status no longer restyles the header; the music glow re-renders its icon only when its size changes.
- `engine/__init__.py` sets `KMP_BLOCKTIME=1` unless already set: CTranslate2's OpenMP threads no longer spin 200 ms after each step. Output was identical, with the same speed and 15–16% less CPU for the app with SenseVoice + NLLB (0.21 → 0.17 cores in the replay). The 27 October gaming pass later uses `0` with one inference thread.
- With the user's approval, the saved settings were switched to local NLLB with the voice detector on; SenseVoice, the QQ loopback, languages and other services were kept. GPU hearing/translation was measured and not adopted (see LATENCY_REPORT.md).

Rejected after measurement: below-normal process priority (a third less translation throughput under realistic load, no measurable probe gain) and forced AVX-512/MKL CTranslate2 backends (slower and changed outputs). All **668 source tests passed**, covering Qwen static prompts, local translation caching, growing/truncated logs, hidden/playing music timers, the OpenMP default, Hy-MT2 routing/output validation and punctuation-only recognition. Built from development commit `425b393`. All **495 bundled-code checks** passed; actual EXE self-check, source/privacy/native-asset checks, localized notices and ZIP integrity passed. Bundled Hy-MT2 code and extracted DLLs matched three real-model source outputs in development Python. An isolated packaged **0.12.14 → 1.0.5** replacement/restart/self-check passed. Saved settings were unchanged. Artifacts are in `dist/1.0.5/`, evidence in `.tools/release-1.0.5/`; no push or GitHub publication. Live headset, Windows 10 and fresh-PC checks remain outstanding.

## 0.12.14 — 2026-10-26 — SteamVR wrist display and main window resizing

The main app now includes the SteamVR wrist display and the resizing fixes below. Its standard EXE keeps the existing GitHub auto-update path. The separate uncommitted local translation/speech experiments are excluded. Saved settings, selected services/models and downloaded model files are preserved. Package and actual GitHub upgrade checks passed.

Published release source `8a67264` (development `3b2b4af`) passed 647 source tests and 380 checks against bundled UI/VR/update/translation bytecode. The actual EXE self-check, VR assets/OpenVR/native/runtime checks, source/privacy scans, ZIP integrity and all five GitHub asset digests passed. Bundled VR texture code passed 600 native GPU uploads/readbacks. Update notices and VR settings rendered correctly in English, Chinese and Vietnamese. The real 0.12.13 → 0.12.14 GitHub upgrade passed download/SHA-256, packaged replacement/restart, new-version self-check and no-update checks. Saved user settings and the four uncommitted local translation/speech files were unchanged. Live headset/controller behavior, Windows 10 and fresh-PC installation remain unverified. Evidence: `.tools/release-0.12.14/`.

### Main window resizing

Narrow windows now place audio controls on a second toolbar row, keeping icons and the VR/settings/window buttons readable. Widening restores the single row. Minimum dimensions follow the controls and language labels, preventing the language selectors from being clipped when the window is shortened or languages change. Audio-device arrows retain their full icon size, and menus and typed text survive reflow.

Before packaging: 197 UI/VR tests passed. Native Windows checks passed 54 resize/language/visibility states in English, Chinese and Vietnamese at 100%, 150% and 200% scaling.

### SteamVR wrist display in the main app

Imported the VR project's wrist overlay, hand model, placement/settings preview, opposite-controller controls, persistent GPU textures and connection recovery. The normal app now exposes a **VR** button and manages the overlay alongside its existing backend, update checks and service-health checks. Existing `vr.json` placements are reused.

Adapted the wrist I / They pickers to the current three-language settings. The wrist uses the shared subtitle view, including progressive translations and same-language mixed-text results. Panel output languages, custom chatbox destinations, selected services/models and the newer speech/translation implementation are preserved. Added OpenVR and the explicit VR assets to the existing build and self-check.

Before packaging: 645 working-tree tests passed, including 81 VR checks; source self-check and isolated Windows startup/shutdown passed. Native OpenGL checks passed 600 uploads/readbacks, and previews were checked in English, Chinese and Vietnamese. The original VR folder and pre-existing local translation/speech fixes were preserved. Live headset/controller behavior remains unverified.

## 0.12.13 — 2026-10-25 — Keep the requested release scope

The user's scope reply was received after 0.12.12 was published: include only latency and translation fixes. This release restores the previous Sound-page detector reset card and the earlier compact project guide. The expanded Obsidian guide is preserved locally outside the release. Version 0.12.12 remains an unchanged historical artifact; 0.12.13 supersedes it.

Online target concurrency, background local translation weight loading, mixed-language translation and display fixes remain unchanged. No model selections, saved settings, detector thresholds or inference parameters are changed. Package and actual GitHub upgrade checks passed.

Published release source `2a5d0a0` (development `f5fcd94`) passed 560 source tests and 323 checks against bundled translation/local-model/UI bytecode, including the restored detector reset control. Actual EXE self-check, source/native/runtime checks, ZIP integrity and all five GitHub asset digests passed. The real 0.12.12 → 0.12.13 upgrade passed download/SHA-256, packaged replacement/restart, new-version self-check and no-update checks. Saved settings were unchanged. Latency/translation implementation is unchanged from 0.12.12; the reset card matches 0.12.11. The compact guide is bundled; the expanded guide is preserved locally outside the release. Live audio and game performance were not retested. Evidence: `.tools/release-0.12.13/` and `.tools/scope-0.12.13/`.

## 0.12.12 — 2026-10-25 — Mixed-language translation and local startup

Mixed Chinese/Japanese/Korean text labelled as English or Vietnamese was previously copied unchanged when the target matched that label. It now reaches the selected translator, including NLLB/Qwen, and its completed translation remains visible even when source/target labels match. Ordinary same-language text still reuses the original. This script check is deliberately limited to English/Vietnamese outputs; it does not solve every code-switching pair or distinguish foreign proper names.

Installed local NLLB/Qwen weights now load on the existing background translation worker at startup, sharing the same lock and models used by typed and spoken text. Missing models are skipped; a failed preload remains retryable on the first request. This moves weight loading out of a later first request when preparation finishes in time; it does not accelerate steady-state decoding or shorten speech capture.

Removed the Voice detector help/reset card and its Restore detector defaults button from Settings → Sound. The existing detector toggle and strictness sliders remain available; saved settings and speech processing are unchanged.

The Obsidian guide now covers setup, architecture, models, latency, costs, release workflow and known limitations in one file. Validation: 559 source tests passed. Real local NLLB replay loaded weights in 1,225 ms before the first request and translated three formerly skipped mixed examples in 199–287 ms. A repeated Chinese input still changed meaning; that model limitation is unresolved. The replay used supplied text and fake recognition, not live audio. EN/ZH/VI Sound-page renders preserved custom settings. Package and actual GitHub upgrade validation passed.

Published release source `2df0d65` (implementation `5ee86df`; development `fbdc497`, documentation `95630d5`) passed 559 source tests, 170 subsequent focused checks and 322 checks against bundled translation/local-model/UI bytecode. Actual EXE self-check, source/native/runtime checks, ZIP integrity and all five GitHub asset digests passed. The real 0.12.11 → 0.12.12 upgrade passed download/SHA-256, packaged replacement/restart, new-version self-check and no-update checks. User settings were unchanged. The local mixed-text replay is a text/model/rendering check, not a live recognition or game-FPS test. NLLB still changes meaning on a repeated Chinese example. Evidence: `.tools/release-0.12.12/` and `.tools/local-translation-diagnosis/`.

## 0.12.11 — 2026-10-25 — Faster multi-language online translation

Online translations previously ran destination by destination. They now run up to two at once per utterance and display whichever completes first. Panel languages are processed before chatbox-only destinations; the original is immediately reused for a source-language output. Duplicate requests, partial-failure handling, panel language order and the single final ordered microphone/chatbox message are preserved.

HTTP client and service-chain initialization are synchronized. Concurrent failures keep their cooldown even if another language succeeds. Local models retain their shared lock and CPU limits. Speech detection, recognition models, prompts and decoding settings are unchanged. New timing logs separate hearing wait, recognition and per-target translation to help diagnose remaining delay.

Five warm paired EN/ZH/VI examples through the selected online service: two-output median **188.8 → 102.8 ms** (~46% less); first output **90.5 → 93.2 ms**. All twelve paired target outputs across six examples were identical; the first phrase's 4.14-second startup pair was excluded from warm timing. This is a small component test, not an end-to-end/FPS or accuracy guarantee. See [LATENCY_REPORT.md](LATENCY_REPORT.md) for method, limits, diagnosis and regression coverage. All 544 tests passed, including per-target timing output to engine.log. Release and upgrade validation passed; see below.

Published release source `a03ab48` (development `8d3b8f8`) passed 544 tests and 43 checks against bundled translation bytecode for concurrent targets, partial results, cooldowns, local isolation and ordered chatbox messages. The actual EXE self-check, bundled native DLL hashes, source/asset scans and ZIP checks passed. All five uploaded GitHub assets matched local sizes/digests. The real 0.12.10 → 0.12.11 upgrade passed download/SHA-256, packaged replacement/restart, new-version self-check and no-update checks. User settings were unchanged. Live recognition errors, game FPS and end-to-end speech latency were not tested. Evidence: `.tools/release-0.12.11/`.

## 0.12.10 — 2026-10-25 — Whisper turbo through Vulkan for AMD PCs

- Added a separate **Whisper turbo · Vulkan (AMD)** hearing choice. Existing NVIDIA CUDA, SenseVoice, PhoWhisper and translation choices are preserved.
- Bundled a pinned whisper.cpp runtime behind a small C ABI; the SDK is only a developer dependency. Downloads use a separate ~547 MiB Q5 model with pinned size/SHA-256 and existing HF-Mirror fallback. Model deletion remains scoped to its own files.
- Keep one GPU context loaded, warm it once, use independent utterances, and release it on model switches/normal worker shutdown. Native GPU failures become hearing errors. Audio stays in memory; no local server or child inference process is used.
- Added regression coverage for selection/reuse/cleanup, GPU errors, Chinese routing, silence/repetition, invalid audio and missing files/runtime. 536 tests passed. Actual RTX 3080 Vulkan inference passed six EN/ZH/VI recorded-clip calls; this is not a SenseVoice comparison or AMD benchmark.
- Initial load/warmup took 20.4 s; later recorded calls took 403–1,625 ms with uncontrolled concurrent GPU load. AMD hardware, mixed-language accuracy and VRChat performance remain unverified. See [native integration notes](native/whisper_vulkan/README.md).


Published release source `f38139a` (development `c3143fd`) passed 536 tests, EXE/source/runtime/license checks, actual packaged Vulkan model load/warmup and a no-compatible-GPU failure without a crash. All five GitHub assets matched their local sizes/digests. The actual 0.12.9 → 0.12.10 GitHub upgrade passed download/SHA-256, replacement/restart, new-version self-check and no-update checks. Real Vulkan recognition was tested on RTX 3080, not AMD. User settings were preserved. Evidence: `.tools/release-0.12.10/` and `.tools/whisper-vulkan/`.

## 0.12.9 — 2026-10-24 — Remove hidden translation fallback for every service

The 0.12.7 fix protected Local Model only. A selected custom domain could still load a legacy per-PC Gemini add-on after its configured model failed. Gemini's error then replaced the actual service error. ART now removes the automatic add-on loader entirely: `ServiceChain` uses only the selected local model or the models explicitly configured for the selected online service. Existing add-on files are preserved but ignored. Explicit comma-separated alternatives within the selected service retain their cooldown/fallback behavior. Switching services remains a user choice.

The Switch Model dialog now shows the configured custom-domain name instead of its internal `custom_…` identifier. Hearing and Translating remain separate selections. A speech-generation model selected for Translating still requires the user to choose a text-capable model; the fix does not silently change settings or make incompatible models work.

The new regression suite installs a legacy Gemini file in an isolated profile and verifies that custom domains, a built-in online service and local translation do not import it. It checks original errors during cooldown, explicit same-service model fallback and switching back to local/another domain. Four cases failed before the fix with the reported Gemini error or unwanted add-on membership. The full suite passed **528 tests**. Release evidence is recorded in the handoff after packaging.

Published release source `a7b09a6` passed 528 tests, bundled routing/error/cooldown and same-service alternative checks, actual EXE startup with an ignored legacy add-on trap, EXE self-check, source/runtime/native DLL checks, ZIP integrity and uploaded asset digests. The actual GitHub upgrade 0.12.8 → 0.12.9 passed download/checksum, replacement/restart, new-version self-check and no-update checks. Provider/model choices and legacy files were preserved; successful inference against the user's custom endpoint remains unverified.

## 0.12.8 — 2026-10-24 — Stable detector adjustment and restore defaults

Changing detector strictness during speech could discard a phrase already in progress or promote a short noise burst into speech. `Segmenter` now captures strictness when each sentence starts and applies later slider changes to the next sentence. Normal fixed-threshold detection is unchanged. Settings → Sound adds **Restore detector defaults**: detection on, microphone 50%, other players 70%. It preserves models/devices/languages and existing saved values until clicked. Help text explains the tradeoff between noise rejection and missed quiet words; all new UI and update-notice text is translated to Chinese and Vietnamese.

The detector code/weights and capture code were unchanged between 0.12.2 and 0.12.7. This is a fix for an existing adjustment defect, not a confirmed post-0.12.2 detector regression. Two regression cases reproduced the defect before the fix; the full suite then passed **524 tests**. Replaying 494 recordings at four fixed thresholds matched 0.12.2 in all 1,976 comparisons. A more permissive speech-counting change was rejected because it admitted additional noise. See [VOICE_DETECTION.md](VOICE_DETECTION.md) for evidence, settings guidance and limits. Release validation is recorded in the handoff after completion.

Published release source `6b3f9c3` passed 524 tests, 1,976 fixed-threshold comparisons, packaged adjustment/defaults/persistence checks in all three UI languages, EXE self-check, source/runtime/native DLL checks, ZIP integrity and uploaded asset digests. Long Settings labels now wrap, and the Vietnamese restore label is shorter; all 107 UI tests were rerun after that layout correction. Native Windows packaged previews and control-boundary checks confirmed EN/ZH/VI controls fit. The actual GitHub upgrade 0.12.7 → 0.12.8 passed download/checksum, replacement/restart, new-version self-check and no-update checks. Live recognition quality remains unverified; use Restore detector defaults to compare microphone 50% with a previously raised setting.

## 0.12.7 — 2026-10-24 — Keep local translation local

An installed Gemini add-on could run after NLLB or Qwen failed, even with **Local Model** selected. Its error replaced the local error, so the overlay could report Gemini while Settings still showed NLLB. `ServiceChain` now includes add-on fallbacks only for online services and loads add-ons only when an online chain is first needed. Local failures retain the original model error, including during the existing cooldown. Switching from an online service back to local also excludes add-ons.

This shared fix covers typed messages and both speech queues. It preserves selected providers, installed models, local inference parameters, cooldowns and online-service fallback behavior. It does not fix every possible local inference error; those errors are now visible instead of being hidden by a later Gemini failure.

Regression checks reproduce the old Gemini error for both local translators, verify zero add-on calls after local success/failure/cooldown/recovery, and cover lazy loading plus online → local switching. All three new cases failed before the routing fix; the full suite passed **521 tests** after it. Packaging and release validation are recorded in the handoff after completion.

Published release source `f06758e` passed 521 tests, packaged local routing/error/cooldown/recovery/service-switch checks, EXE self-check, source/runtime/native DLL checks, ZIP integrity and all uploaded asset digests. The real GitHub upgrade from 0.12.6 to 0.12.7 passed download/SHA-256 verification, replacement/restart, new-version self-check and no-update checks. Live VRChat audio was not retested; local inference behavior is unchanged.

## 0.12.6 — 2026-10-23 — Delete local models and Obsidian project guide

Local model cards now show **Delete** when app-managed weights or partial downloads exist. The first click offers **Confirm delete / Cancel** in the same card. Deletion is disabled while any model download is active. A cleanup-only card offers deletion of retired non-turbo Whisper large-v3 files without restoring its download option. Successful deletion refreshes Settings and allows available models to be downloaded again.

`engine/local_model.py` enumerates only the chosen model's pinned file paths and partials, validates every resolved target before unlinking, and removes only empty parent directories. It preserves other models, unknown files, shared NVIDIA libraries and provider settings. Redirected paths are refused; file-in-use errors are shown and can be retried. Explicit turbo deletion creates `whisper.deleted` so the existing source-install fallback does not immediately fetch weights again. The Delete action does not clean external Hugging Face caches or unload model objects already held in memory; stop using the model/restart if Windows holds a file open. Repair pointers: inspect `_owned_files`, `delete`, `missing`, and `LocalModelDialog.delete_model` together; never replace this with deletion of the entire cache.

Added [ART Project Guide](ART%20Project%20Guide.md), a self-contained Obsidian-ready note with YAML metadata, diagrams, architecture and folder maps, language controls, storage paths, model tradeoffs, release workflow and troubleshooting. It contains no API credentials. Companion links work when the repository's Markdown notes are also in the vault.

Validation for 0.12.6: 518 tests passed, including all model deletion targets, incomplete downloads, preserved shared files/settings, validation before mutation, redirected paths, file-in-use errors, cache redownload suppression, inline confirmation/cancel, download blocking and retired-model cleanup. Published from release source `ce06fb9`. Packaged self-check and isolated UI deletion/cancel/retired-cleanup checks passed; native DLL/runtime/manifest/source checks, ZIP integrity and all five uploaded asset digests passed. The ZIP includes the Obsidian guide. Actual GitHub upgrade 0.12.5 → 0.12.6, restart, self-check and no-update check passed. See AGENT_HANDOFF.md for hashes/evidence.

## 0.12.5 — 2026-10-23 — PhoWhisper, Qwen and clearer model choices

Removed the non-turbo Whisper large-v3 chooser entry at the user's request. Existing files remain intact; a saved removed choice resolves to turbo. Added PhoWhisper Small for Vietnamese hearing on CPU INT8 (no NVIDIA download), plus Qwen3 1.7B INT8 as an optional CPU translator. Each model card explains supported app languages, specialization and hardware/speed tradeoffs in English, Vietnamese and Chinese. NLLB stays the low-latency default; merely installing this update does not select a new provider.

`LocalWhisper` loads PhoWhisper's own pinned folder with two CPU threads and Vietnamese warm-up. It rejects explicitly unsupported languages and drops Auto results detected as non-Vietnamese. Turbo's GPU behavior is preserved. `LocalQwenTranslator` uses CTranslate2 Generator and the pinned non-thinking Qwen3 prefix; source and target prompts reuse `chat_messages`. Greedy output is limited to 512 tokens, input to 1,024 tokens. Incomplete EOS, repeated/empty/reasoning or obvious wrong-script output fails through `TranslateError`. `services.translate_models` resolves the local selection and `ServiceChain` routes both typed and speech translation correctly. Both local translators share a lock, releasing the other weights when loading.

Validation: **505 tests passed**, including selection migration, CPU readiness, PhoWhisper routing, translator switching/reuse, non-thinking prompts, truncation/repetition guards and translated model cards. Real downloads passed SHA-256 and both new models ran on CPU. Two Vietnamese recording replays matched reference words. The 0.6B Qwen conversion failed basic translation checks; the selected 1.7B option performed better but remains slower than NLLB. See LATENCY_REPORT.md and LOCAL_TRANSLATION_PLAN.md for evidence and limits. Model wording, broad accent coverage, mixed speech and mainland-China downloads still need real-world checking. Published v0.12.5 from release source `11a5a16`. The packaged self-check and real PhoWhisper/Qwen inference passed, along with native-DLL/runtime/manifest checks, source scanning, ZIP integrity and all five GitHub asset digests. Actual GitHub upgrade 0.12.4 → 0.12.5, restart, self-check and no-update check passed. Hashes and evidence are recorded in AGENT_HANDOFF.md. Previews closed automatically after 12 seconds.

Repair pointers: compare model IDs across `MODELS`, `local_models.json`, `services.translate_models` and `ServiceChain`; verify CTranslate2 >=4.8.2 and the exact pinned tokenizer before changing Qwen's prompt. Never remove the empty thinking prefix or accept a length-capped answer as complete. NLLB's sentence and loop handling is unchanged. If CPU latency is too high, choose NLLB for translation and GPU turbo for multilingual hearing; do not silently lower decoding quality or activate a different provider.

### HF-Mirror fallback and agent handoff

The user authorized keeping Hugging Face and using `https://hf-mirror.com/` when the original model download cannot connect. `engine/local_model.py::_fetch` now switches to the same pinned file path on HF-Mirror after a connection interruption, short response or refused HTTP response. Partial files retain Range resume; a full 200 response restarts safely. The original size and SHA-256 still gate installation. Cancellation and file-open/write errors do not switch hosts; mirror retries are bounded. Oversized responses are discarded rather than repeatedly downloaded. Non-Hugging-Face hosts are unchanged.

Validation: **490 tests passed**, including 39 focused downloader/local-model/offline-installer tests. Added cases cover primary success, HTTP/network failure, resume across sources, ignored Range, mirror corruption, both sources unavailable, bounded retries, cancellation, disk failure and oversized output. A real pinned NLLB `config.json` download passed SHA-256 after simulated primary failure, but the mirror redirected back to Hugging Face. This does not prove availability in mainland China or a full weights download.

[AGENT_HANDOFF.md](AGENT_HANDOFF.md) records current release/source status, completed behavior, measured latency, open model choices, safe export/build steps and next checks. The fallback was committed after v0.12.4 and is included in v0.12.5. No provider setting or prior release asset was changed. The model additions/removal above were authorized by the later request; Hy-MT2 is still a candidate.

## 0.12.4 — 2026-10-22 — Multiple chatbox languages

Your microphone and typed Send → Auto now follow every selected **They speak** language, rather than only one destination. With English speech and Chinese + Vietnamese listeners, one microphone chatbox message contains English, Chinese and Vietnamese on separate lines. **Settings → Translation → Chatbox languages** offers Follow 'They speak' (default) or up to three Custom languages. **Translated to** continues to control only panel outputs. An explicit Send language still overrides destinations for typed messages only. Auto-detect follows the last heard language, or English before one is heard. Optional Add Speaker words keeps its existing first-panel-language behavior.

`Settings.chatbox_languages` resolves these choices; the config loader validates custom selections. `Utterance.chatbox_targets` captures each message's destinations before queued work starts. `SpeechEngine.finish` and `LiveBackend._run` pass the ordered union of chatbox and panel targets through `translate_targets`, reusing shared results and original text for matching source languages. Successful outputs survive errors in other targets. `LiveBackend._queue_for_chatbox` uses `fit_lines` to deduplicate and share the 144-character budget across original plus up to three translations. No separate OSC messages are created. Single-language typed messages retain their existing optional `translation (original)` format.

Latency: overlapping languages add no translation calls. A new distinct target still adds inference time; requests remain sequential and chatbox delivery waits for completion. Speech recognition, inference settings, fallback handling and OSC pacing are unchanged. To investigate missing chatbox languages, inspect captured `chatbox_targets`, per-target `chatbox_translations`, the explicit Send override and each utterance's error note. Changing choices during a queued message affects subsequent messages only.

Validation: all 479 tests passed. Regression checks cover reuse, source-language matches, partial/all failures, custom targets, typed overrides, captured choices, saved settings, UI synchronization, four-line truncation and duplicate removal. A native Windows preview verified the Settings control and update notice, then closed automatically after 12 seconds. Live reception by another VRChat player is not verified for this change.

## 0.12.3 — 2026-10-22 — Local translation and microphone setup fixes

### Optional offline NLLB installation package

Added `ART-NLLB-200-CT2-offline.zip` as a separate release asset for PCs unable to download the model from Hugging Face. This does not change the v0.12.3 EXE or its update behavior. Download once on a working connection, transfer/extract the ZIP, and run `Install-NLLB.cmd` on the destination PC. The installer is fully offline, needs no administrator or Python, checks source and copied files with SHA-256, and preserves a previous model folder before replacement. No microphone, API or app preferences are changed.

`tools/package_nllb_offline.py` packages only the four files pinned in `engine/assets/local_models.json`, plus the installer, manifest, instructions and model attribution. `tools/install_nllb_offline.ps1` installs into the current user's model cache. The package contains the original pinned CTranslate2 INT8 files, with the model's CC BY-NC 4.0 notice. `tests/test_nllb_offline.py` covers installation, repeat installation, backups, damaged/missing files, duplicate entries and unsafe filenames. A mirror probe redirected to Hugging Face/CDN hosts on the test connection; mainland-China connectivity has not been verified. The offline package avoids that dependency during installation, but still needs a working download or file-transfer route to reach the PC.

Validation: 44 focused installer, model-download and updater tests passed. The final ZIP passed CRC and checksum verification, installed into an isolated cache using Windows PowerShell, was detected as Ready by ART, and translated the two-sentence VR example with the real model. The current user's installed model was left intact.

### Local translation repeats or drops a later sentence

**Cause:** replaying the reported text with the installed NLLB/CTranslate2 model reproduced both failures before rendering: a short, stuttered Chinese input expanded into a 256-token English repetition loop, and “Can you wait a bit? I want to move to VR first.” returned only the first Chinese sentence. The overlay and chatbox did not remove the missing sentence.

**Fix:** `engine/local_inference.py::LocalTranslator.translate` batches separately punctuated sentences, keeping their order and language prefixes. `translation_sentences` preserves common abbreviations, initials, decimal points, URLs and closing quotes. A missing or empty sentence result raises an error instead of returning an incomplete success.

`translation_loop` detects a four-token sequence repeated at least six times in output that has grown to at least 48 tokens and twice its source length. Only that sentence is retried once with `no_repeat_ngram_size=4`; persistent repetition becomes an ordinary translation error. A warning in `engine.log` identifies the retry. Normal single-sentence decoding, CPU thread counts and the shared model lock are unchanged. The repetition setting is documented in the [CTranslate2 API](https://opennmt.net/CTranslate2/python/ctranslate2.Translator.html).

**Verification and limits:** the real-model replay retained both sentences, including VR, and replaced the large repeated block with a bounded answer. Three ordinary single-sentence outputs were unchanged. Regression tests in `tests/test_local_translation_quality.py` cover punctuation, legitimate repetitions, ordered sentence results, empty/missing results and the one-retry limit. All 463 tests passed. Sentence boundaries are conservative punctuation rules and may miss ambiguous abbreviations or unpunctuated speech. Translating sentences separately can lose context between sentences. A repetition retry adds latency to the failed sentence; it does not correct misrecognized speech or guarantee the model's wording. No live microphone/VRChat audio was replayed.

**To diagnose or undo:** check the original recognition first, then look for `Local NLLB repetition detected` in the log. The behavior is confined to `engine/local_inference.py`; cloud providers, speech recognition and the progressive subtitle change in 0.12.2 are separate. Reverting this change should also update its tests and release notice, and any published replacement binary needs a new version.

### Mixer installed on a different microphone

**Cause:** setup treated a selected microphone with no attachment as a new installation, even when the mixer was already registered on another device. The registration guard then refused installation with a generic backup/removal error. A read-only check on the affected PC found a validated Virtual Desktop Audio attachment with all 19 registry entries matching its journal; HyperX QuadCast was selected in the dialog.

**Fix:** `vrc/apo_install.py::registered_microphone` identifies the validated installation and checks its files and registry. `MusicDialog.refresh` shows the existing device and a **Use [microphone]** button instead of another Install prompt. Clicking it rechecks the installation and active endpoint, changes the translator microphone, and signals `MainWindow.settings_changed` to save/apply the selection. The installer also names the existing device if invoked directly.

**To troubleshoot:** choose the installed microphone in both the translator and VRChat, select a running app under Music source, then press Play. Moving the mixer to another microphone still requires removing the old attachment using its rollback journal; this fix does not silently move it or restart Windows audio. If the saved configuration differs from Windows, the existing guard still refuses to overwrite it.

Regression tests in `tests/test_apo_install.py` and `tests/test_music_dialog.py` cover suppression of a second installation/UAC, validation of existing state, saving the selected device, enabling Play after selecting a source app, and rejecting a disconnected microphone before changing settings. These are included in the 463 passing tests above. A native Windows check verified the existing-device message and selection button against the actual saved attachment, then closed the window. No installation or music playback was performed on the affected PC for this fix.

## 0.12.2 — 2026-10-22 — Earlier multilingual subtitles

Implementation commit: [5672680](https://github.com/SentoMinh/ART-Asia-realtime-Translator/commit/5672680aac4ccf3afd8ed689fd4a4ac89108e835). The corresponding development checkout commit is `5587160`.

### What changed and why

Previously, choosing three translation languages made the panel wait for all three requests to finish before showing any translation. The first result was already available but remained hidden while the next requests ran.

Now each completed panel translation appears while the remaining languages continue. The same subtitle row is updated, with a “translating…” indicator until completion. This applies to microphone speech, other players and typed messages.

This reduces the wait for the first visible translation. It does not make model inference faster, shorten the total time for all translations, or send chatbox messages earlier. Requests still run in their original order. Recognition thresholds, model parameters, request counts, fallback cooldowns and OSC pacing are unchanged.

### Code to inspect when fixing it

| File / function | Responsibility |
|---|---|
| [`vrc/translate.py`](vrc/translate.py), `translate_targets` | Optional `on_result` callback receives a dictionary snapshot after an intermediate successful result. The final result and errors still return normally. Targets remain deduplicated; source-language matches reuse the original text. |
| [`engine/speech.py`](engine/speech.py), `SpeechEngine.finish` | Callback emits a separate `Utterance` copy with the same ID, `final=False`, and completed `panel_translations`. The normal completion path handles errors and chatbox sending. |
| [`ui/live_backend.py`](ui/live_backend.py), `LiveBackend._run` | Performs the same partial updates for typed messages through Qt signals. `_on_translated` retains final processing and sending. |
| [`ui/log_view.py`](ui/log_view.py), `LogRow.refresh` | Renders available translations even when `final=False`, hides unfinished outputs, and removes the indicator at completion. |

### Troubleshooting

- **Still waits for every language:** check that both worker paths pass `on_result`, then check the non-final rendering condition in `LogRow.refresh`. A slow first request still delays the first translated output; this change does not parallelize requests.
- **Duplicate rows or chatbox messages:** partial updates must retain the original utterance ID and emit only the display signal. Never route a partial update through `_queue_for_chatbox` or `send_to_chatbox`.
- **Earlier subtitles change unexpectedly:** keep separate utterance copies and immutable translation tuples. Do not mutate an object already emitted to the UI.
- **A later translation fails:** successful outputs must remain visible; the final update reports errors. Preserve the existing fallback chain.
- **Timing logs still show the old delay:** the speech log’s `done in … ms` measures final completion, not the first visible translation. That total is expected to remain similar.

To disable only the earlier display, remove `on_result=show_progress` from both translation call sites and remove their now-unused callbacks. Final rendering and translation results can remain as they are. Do not execute a whole-commit revert unless you also intend to undo the version, notice, tests and documentation bundled in that commit. Any rebuilt release should get a new version number.

### Evidence and regression checks

Controlled benchmark: five runs per case, with a simulated 120 ms delay per translation. Values are medians, not live API or speech-recognition measurements.

| Selected destinations | First visible result before / after | All results before / after |
|---|---|---|
| 1 | 120.3 / 120.5 ms | 120.3 / 120.5 ms |
| 3 | 361.0 / 120.5 ms | 361.0 / 361.2 ms |

All **443 tests passed** for the release. Relevant regression tests:

- `tests/test_engine.py::test_panel_results_arrive_before_later_translations_without_extra_sends`
- `tests/test_typing.py::test_typed_partial_results_do_not_send_or_mutate_earlier_updates`
- `tests/test_typing.py::test_worker_delivers_first_subtitle_while_later_language_is_blocked`
- `tests/test_ui.py::test_panel_partial_results_update_one_row_and_keep_selection`

Run the affected suites after a fix:

```powershell
.venv-app/Scripts/python.exe -m pytest tests/test_engine.py tests/test_typing.py tests/test_ui.py -q
```

The packaged self-check, uploaded checksums and automatic upgrade from 0.12.1 to 0.12.2 also passed. Live VRChat audio and external-service latency were not tested for this change.
