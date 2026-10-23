# Change log

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
