# Voice detection: behavior and repair notes

Detector evidence: 24 October 2026, version 0.12.8. The reset-card instructions apply again in 0.12.13.

## What strictness changes

The detector decides which audio reaches speech recognition. Strictness is its confidence threshold, not a translation-quality control. Raising it rejects more uncertain audio, including quiet speech; lowering it can admit music or noise that the recognition model then mistakes for words. Translation cannot recover words that recognition never received.

Start with **Settings → Sound → Restore detector defaults**: detection on, microphone **50%**, other players **70%**. The button saves only those three settings. Model choices, audio devices and languages are preserved. Existing installations retain their saved strictness until the user changes it or clicks Restore.

If words are missing, reduce the affected source's strictness gradually. If music or room noise creates subtitles, raise it gradually. The two sliders are independent. Turning the detector off uses fixed four-second chunks; it can split words and admit background sound.

## Comparison with 0.12.2

The archived 0.12.2 release source and 0.12.7 have identical `engine/vad.py`, detector weights and `vrc/audio.py` after normalizing line endings. Speech scheduling/segmentation was unchanged; later speech changes added chatbox translation targets. Recognition changes added a separate PhoWhisper path without changing existing Whisper turbo decoding. These comparisons do not establish why a particular live session sounded worse.

The 0.12.8 fix addresses an existing defect in `Segmenter`: `configure()` could change the threshold during an active sentence. Raising it could discard a quiet phrase already underway; lowering it could count the rest of a short noise burst as speech. The segmenter now captures the threshold when a sentence starts and uses it until that segment ends. The latest slider value applies to the next segment, including after a maximum-length cut. Switching the detector on/off still clears pending audio as before.

Two parameterized regressions fail before this fix and pass afterward. They check both directions of change and that the next sentence uses the new threshold. A UI regression verifies restoring defaults, saved values and preservation of selected models/device.

## Recorded-audio checks

The existing development corpus contains 494 clips: 120 microphone, 120 player voice, 120 voice plus quieter music, 120 voice plus louder music, and 14 music/noise-only clips. The bundled ONNX detector was run on all recordings. One clip also produced identical probabilities in a whole-clip call and successive three-frame calls.

Replaying those probabilities through the archived 0.12.2 and fixed segmenters at 50%, 70%, 71% and 90% produced **identical segment lengths and forced-cut flags in all 1,976 comparisons** when strictness remained fixed. The fix does not change normal detection thresholds, sentence silence, pre-roll, minimum speech duration or model inference.

Baseline results at two defaults:

| Threshold | Microphone clips detected | Player voice clips detected | Voice + quieter music detected | Voice + louder music detected | Noise-only clips admitted |
| --- | --- | --- | --- | --- | --- |
| 50% | 120/120 | 120/120 | 120/120 | 120/120 | 2/14 |
| 70% | 120/120 | 120/120 | 120/120 | 120/120 | 1/14 |

“Detected” means at least one segment was emitted. It does **not** mean all words were captured, recognized or translated correctly. These are results from the app's segmenter; an older benchmark used the upstream library's segmentation and reported different noise rejection.

A proposed change counting all lower-confidence continuation frames toward minimum speech was rejected: at 50% it admitted a third noise-only clip; at 70% it admitted an additional noise segment. It is not in the release.

Development evidence is under `.tools/vad-0.12.8/`: `probabilities.json`, `comparison.json`, `final-replay.json`, plus the scripts that generated them. Recordings and these large artifacts are not bundled or exported. Packaged and publication evidence is recorded in [[AGENT_HANDOFF]].

## Limits and next diagnosis

No live microphone was recorded, and recognition/translation accuracy was not re-benchmarked for this change. The report does not prove a general accuracy improvement over 0.12.2 or resolve speech that is still missed at an unchanged threshold.

For a remaining problem, distinguish missing original text from a bad translation of correct original text. Check the chosen audio device, hearing model and selected spoken languages. The existing `engine.log` reports audio arriving, peaks, emitted sentences and engine errors. A short, consented failing recording with the threshold/model noted would allow a direct old/new comparison without guessing from translated text.
