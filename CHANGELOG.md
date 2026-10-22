# Change log

## 0.12.3 — 2026-10-22 — Local translation and microphone setup fixes

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
