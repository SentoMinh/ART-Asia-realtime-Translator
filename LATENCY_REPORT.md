# ART latency measurements — 22–23 October 2026

Measured with ART **0.12.4**, source commit `9c5a96c` in the release repository, starting at 15:27:58 UTC. **Local execution was faster in this run.** These are current component timings, not a measured speedup over an older app version.

## Environment and method

- Windows PC: Ryzen 7 7800X3D, RTX 3080 10 GB. VRChat was not running. GPU usage before the test was 0%, with about 2 GB already allocated by other processes.
- Saved configuration: Modal `sensevoice-cpu` for hearing, local `nllb-200-ct2` for translation. Modal also advertises `nllb-200-ct2`. Local Whisper large-v3-turbo and NLLB were ready; local SenseVoice and Whisper large-v3 were not ready and were not downloaded.
- Production `ServiceTranslator`, `LocalTranslator`, `CloudHearing`, `LocalWhisper` and `translate_targets` adapters were used directly. No fallback chain was used. The Modal HTTP client was reused with a 60-second timeout. No capture, OSC sending, provider-setting changes or model downloads occurred.
- Translation: six short conversational inputs covering EN→ZH, EN→VI, ZH→EN, ZH→VI, VI→EN and VI→ZH, each repeated three times (18 warm calls per engine). Local/remote execution order alternated by round. The first request for each engine was recorded separately.
- Three-output translation: one English phrase translated sequentially to Chinese, Vietnamese and Japanese, three repetitions per engine. All three targets differ from the source. A source-language panel output instead reuses the original and needs no inference.
- Hearing: existing clean FLEURS recordings, loaded before timing. Shared EN/ZH comparison uses four recordings of 6.48–7.68 seconds, repeated twice in each language mode (8 calls per engine/mode). Local Whisper additionally ran two Vietnamese recordings; they are excluded from the shared EN/ZH table. Each engine was loaded once and given one first request before warm measurements. Modal hearing ran after Modal translation, so its first request is not a separate cold-service test.
- Timings use `perf_counter`, include network/serialization for Modal, and stop when a complete adapter result returns. They exclude recording duration, sentence-end detection, worker queues, Qt rendering and OSC pacing. Hearing was measured in blocks by engine; background load/network variation is not controlled.
- Runtime versions: CTranslate2 4.8.2, faster-whisper 1.2.1, httpx 0.28.1, tokenizers 0.23.2. Local NLLB uses CPU INT8, one worker/two intra-op threads and beam size 1; local Whisper uses GPU FP16 and beam size 5. Remote hardware, model hash, server revision and decoding options were not verified. Matching advertised model names do not prove identical execution settings.

## Warm results

Median / sample p95, in milliseconds. p95 uses the nearest-rank observation; these small repeated samples do not establish production tail latency.

| Component | Modal | Local | Calls per engine |
| --- | ---: | ---: | ---: |
| NLLB translation, one target | 561 / 786 | 299 / 631 | 18 |
| NLLB, all three targets complete | 1,477 / 1,485 | 635 / 677 | 3 |
| Hearing, EN/ZH, Auto | SenseVoice: 1,160 / 1,213 | Whisper turbo: 311 / 401 | 8 |
| Hearing, EN/ZH, selected language | SenseVoice: 1,167 / 1,203 | Whisper turbo: 246 / 382 | 8 |

For three translation targets, the median time to the first completed translated result was **530 ms on Modal** and **242 ms locally**. Final completion remained **1,477 ms** and **635 ms** respectively. These are helper-callback timings, not screen-presentation timestamps.

Warm local translation took about **47% less time** than Modal in this sample. Auto-mode local hearing took about **73% less time**, but the recognizers differ: this does not isolate cloud overhead or establish which recognizer is more accurate. SenseVoice does not support Vietnamese; Whisper does.

There were no request exceptions, empty hearing results or detected-language mismatches in the measured warm hearing calls. This is not a formal speech-recognition accuracy evaluation.

## Startup and first-request behavior

| Measurement | Observed time |
| --- | ---: |
| Modal NLLB first request | 26.304 s |
| Local NLLB first request, including lazy model load | 1.875 s |
| Local Whisper load, including the existing silence warm-up | 3.910 s |
| Local Whisper first real clip after load | 0.157 s |
| Modal SenseVoice first clip, after translation had already used the service | 1.458 s |

The long first Modal request is consistent with startup or service queuing, but no server logs were inspected, so a cold start is not confirmed. It is one observation, not a typical cold-start estimate. Local load times can also benefit from the operating system's file cache.

## Quality issue found during timing

The Modal endpoint returned incomplete results for two multi-sentence inputs in every repetition:

| Input | Modal output | Local output |
| --- | --- | --- |
| EN→VI: “Can you wait a bit? I want to move to VR first.” | “Anh có thể đợi một chút không?” — the VR sentence is missing | “Anh có thể đợi được không? Tôi muốn chuyển sang VR trước.” |
| ZH→EN: “你可以等一下吗？我想先切换到VR。” | “I'm going to switch to VR.” — the question is missing | “Can you wait? I'd like to switch to VR first.” |

That is **6 incomplete responses among 18 warm Modal translation calls**, representing two distinct inputs repeated three times. They returned successfully at the API level, so zero request errors must not be interpreted as zero quality failures. This is a small targeted regression sample, not an overall error-rate estimate. Local output retained both sentences for these cases; translation quality was not comprehensively graded.

The app's local NLLB path splits punctuated sentences and batches them, with a bounded retry for excessive repetition. The custom-domain NLLB adapter sends the complete text to `/translate` and uses the returned text. The remote implementation was not inspected or changed in this task.

## What the latency changes actually improved

1. **0.12.2: earlier panel results.** `SpeechEngine.finish` and `LiveBackend._run` emit completed translations through `translate_targets(on_result=...)` while later targets continue. The old implementation withheld all outputs until the end. This reduces first-visible-result waiting; it does not accelerate model inference or final chatbox delivery.
2. **0.12.4: reuse across chatbox and panel destinations.** The ordered union of destinations is translated once. A matching source language reuses the original. This prevents duplicate requests as chatbox languages expand; new distinct destinations still add inference work.
3. **Existing reuse and warm-up remain.** Local models stay loaded; the local translator is shared and protected by its existing lock. Whisper already performs a silence warm-up during loading. These were not newly added by the recent latency-display change.
4. **0.12.3's sentence/repetition fix was for correctness.** Batching sentences preserves later sentences; a problematic sentence can be retried once. That retry can add latency and is not a speed optimization.

The controlled test used exactly 120 ms per translation, five runs per case, without network or real model inference:

| Three-target panel | First result | All results |
| --- | ---: | ---: |
| Before the progressive-display change, saved baseline | 361.0 ms | 361.0 ms |
| Current 0.12.4 rerun | 120.5 ms | 361.5 ms |

This confirms roughly **240 ms less waiting for the first result** in that controlled example, not a claim of 240 ms faster real inference.

## Language selection and remaining delay

On the shared EN/ZH clips, explicitly selecting a language reduced Whisper's median from 311 to 246 ms. Modal SenseVoice showed no meaningful speed benefit (1,160 vs 1,167 ms). Do not generalize this small test to all models or accuracy.

Language selection is model-dependent: the local SenseVoice recognizer is constructed in Auto mode. With multiple selected languages, the app still uses detection and filters results outside the selection afterward. The Whisper path deliberately lets Mandarin/Cantonese detection run when Chinese is selected. Picking a language therefore does not always bypass detection or force a restricted decoder vocabulary.

The sentence-end detector still waits **0.8 seconds of quiet**. This was intentionally retained because the previous 0.55-second setting cut speech at breaths. Worker queueing, additional output languages, HTTP/server queueing and the existing minimum OSC send gap can add delay. Do not sum the table's medians and present that as a measured end-to-end result.

## Evidence and limits

The development workspace retains the bounded harness and raw samples in `.tools/latency-2026-10-22/measure.py`, `results.json`, `progress.log`, and `panel-current.json`; those local artifacts contain no API credentials or endpoint URLs. Audio comes from the existing FLEURS benchmark described in [BENCHMARK.md](BENCHMARK.md): `en_1555`, `en_1537`, `zh_1555`, `zh_1537`, and local-only `vi_1559`, `vi_1607`.

No application behavior or selected providers changed during this measurement. The published v0.12.4 EXE is unchanged. Real VRChat contention, noisy live speech, remote reception, sustained traffic, server cold-start frequency and a broad translation-quality comparison remain unmeasured. Keep the latency-first decision rule and quality checks in [LOCAL_TRANSLATION_PLAN.md](LOCAL_TRANSLATION_PLAN.md).


## 23 October: NLLB versus the new Qwen3 1.7B option

The same six EN/ZH/VI conversational inputs above were replayed through the production local adapters, with `heard=True`, in three rounds per model. The first full round was excluded from warm statistics; the remaining 12 calls per model form this small sample. Models ran sequentially in blocks, on CPU INT8 with two intra-op threads and one worker, using CTranslate2 4.8.2 and tokenizers 0.23.2. **VRChat was running**, but game scene/load was not controlled; this is not a controlled contention benchmark or end-to-end speech latency test. No microphone capture, OSC or remote inference was used, and provider settings were unchanged.

| Translator | First call including load | Warm median | Warm range |
| --- | ---: | ---: | ---: |
| Existing NLLB-200 CT2 | 2,141 ms | **294 ms** | 252–393 ms |
| Qwen3 1.7B CT2 INT8 | 4,358 ms | **2,218 ms** | 1,603–2,758 ms |

NLLB stays the default for low latency. Qwen is an optional alternative, not a speed improvement. Qwen uses the same translation-only chat prompt as the online adapter, the pinned non-thinking assistant prefix, greedy generation, a 1,024-token input limit and 512-token output limit. This replay preceded the final Chinese script normalization (Traditional output converted to Simplified for `zh`); normalization does not alter generation settings. No statistically meaningful p95 or quality win is claimed from this sample.

All replay calls completed, but meaning is not perfect: the English “move to VR first” became Vietnamese “try VR first” with Qwen, and “first” was omitted in one Chinese-to-English example. Basic Japanese/Korean/Cantonese output was also exercised separately; naturalness and Cantonese correctness need language-competent review. The tested Qwen3 0.6B community conversion copied source text or altered meaning on basic checks and was rejected. These observations concern the tested files/template, not every quantization or deployment of that model.

PhoWhisper Small CPU INT8/two threads loaded and warmed in 4,877 ms. Two Vietnamese recordings matched reference words, ignoring case. Forced Vietnamese decoding took 2,428 and 2,081 ms; Auto took 4,209 and 3,621 ms. This supports offering PhoWhisper as a Vietnamese CPU specialist, not claiming it is faster than GPU Whisper turbo or validated for mixed speech.

Exact revisions/download hashes are in `engine/assets/local_models.json`; attribution and limits are in [LOCAL_TRANSLATION_PLAN.md](LOCAL_TRANSLATION_PLAN.md). Ignored local evidence: `.tools/model-additions/comparison.json`, `pho-smoke.json`, `qwen-1.7-smoke.json`. The new weights and existing benchmark recordings are not included in source exports or the EXE.
