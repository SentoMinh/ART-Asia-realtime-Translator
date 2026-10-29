# Project priorities

Updated 2026-10-27 to reflect completed research and optimizations. See [AGENT_HANDOFF.md](AGENT_HANDOFF.md) for current source/release status and [LATENCY_REPORT.md](LATENCY_REPORT.md) for the research and evidence index.

## Current focus

Improve voice recognition accuracy, responsiveness and reliability while leaving CPU and memory capacity for VRChat and other heavy tasks. The gaming resource budget is implemented in source (`1efb598`); live game-FPS/headset checks and a fresh process-priority comparison remain outstanding. Keep recognizing speech from the existing audio sources; identifying which person spoke is outside the current scope.

## Local translation: latency first

Version 0.12.5 keeps Hugging Face downloads and falls back to HF-Mirror. A small-file probe redirected back to Hugging Face, so a successful test from the friend's connection in China is still needed. The user prefers an online download flow; retain the offline package as an existing alternative without making it the only proposed solution. The user explicitly approved removing non-turbo Whisper large-v3 and adding PhoWhisper plus a light Qwen. Both additions are implemented; Hy-MT2 1.8B Q4_K_M was subsequently compared and included in local release 1.0.5.

The user's preference is **low latency first**, with other model options available as alternatives. Choose the fastest measured local translator that still preserves the meaning; do not select a default by model size, popularity or quality benchmarks alone. Keep translation offline after setup and provide a download/transfer route usable by people in China.

Read [LOCAL_TRANSLATION_PLAN.md](LOCAL_TRANSLATION_PLAN.md) before selecting or integrating another model. Qwen3 1.7B INT8 and Hy-MT2 1.8B are optional implemented choices; NLLB remains the default after faster replay results. The tested Qwen 0.6B conversion failed basic checks, and Qwen2.5 3B was slower and left Chinese untranslated, so neither is offered. Other model sizes remain optional research candidates, not approved additions or replacements. The current CUDA path covers NLLB/Qwen only; Hy-MT2 remains CPU-only.

## Deferred: speaker identification

Revisit distinguishing and consistently labeling different people as Speaker 1 / Speaker 2 (speaker diarization) in a future feature discussion. These labels in the demo are examples; the live recognition engine currently receives mixed audio and does not identify individual people.

Remind the user of this deferred idea when planning the next project features. This is a saved project note, not a scheduled notification; no reminder date has been specified.

## Preview handling

Temporary demo previews opened during development should close automatically after a short preview or be closed when verification finishes. Do not leave demo instances running after completing a task.
