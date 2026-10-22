# Project priorities

Updated 2026-10-22 at the user's request.

## Current focus

Improve voice recognition accuracy, responsiveness and reliability. Keep recognizing speech from the existing audio sources; identifying which person spoke is outside the current scope.

## Local translation: latency first

The user's preference is **low latency first**, with other model options available as alternatives. Choose the fastest measured local translator that still preserves the meaning; do not select a default by model size, popularity or quality benchmarks alone. Keep translation offline after setup and provide a download/transfer route usable by people in China.

Read [LOCAL_TRANSLATION_PLAN.md](LOCAL_TRANSLATION_PLAN.md) before selecting or integrating another model. Compare small Qwen models with thinking disabled against the existing NLLB/CTranslate2 baseline; include Tencent Hy-MT2-1.8B as the translation-specialized alternative. Larger models are optional comparisons if smaller models fail the quality checks. These are candidates, not a verified speed ranking or installed features.

## Deferred: speaker identification

Revisit distinguishing and consistently labeling different people as Speaker 1 / Speaker 2 (speaker diarization) in a future feature discussion. These labels in the demo are examples; the live recognition engine currently receives mixed audio and does not identify individual people.

Remind the user of this deferred idea when planning the next project features. This is a saved project note, not a scheduled notification; no reminder date has been specified.

## Preview handling

Temporary demo previews opened during development should close automatically after a short preview or be closed when verification finishes. Do not leave demo instances running after completing a task.
