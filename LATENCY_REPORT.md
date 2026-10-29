# ART latency measurements — 22–27 October 2026

## Research and optimization record

This file records measurements and rejected performance choices. [CHANGELOG.md](CHANGELOG.md) records the resulting implementation; [AGENT_HANDOFF.md](AGENT_HANDOFF.md) distinguishes current source from built releases. Existing research and validation are indexed below so a completed experiment is not mistaken for an unfinished proposal.

| Work completed | Result / decision | Detailed record and local evidence |
| --- | --- | --- |
| Hearing, translation and Cantonese evaluation | Compared recognition/translation engines and detector behavior; results apply to the recorded test sets. | [BENCHMARK.md](BENCHMARK.md), [VOICE_DETECTION.md](VOICE_DETECTION.md), `bench/results/` |
| Local model and download research | Added PhoWhisper and Qwen3 1.7B, kept Hugging Face with HF-Mirror fallback; the tested Qwen 0.6B conversion was rejected. China connectivity remains unverified. | [LOCAL_TRANSLATION_PLAN.md](LOCAL_TRANSLATION_PLAN.md), `.tools/model-additions/` |
| Online translation latency | Two concurrent target requests reduced two-target completion time about 46% on five warm paired examples; ordered final chatbox output preserved. | 25 October section below; `.tools/latency-0.12.11/` |
| Mixed-language correctness and local startup | Mixed CJK text labelled EN/VI reaches translation; installed local weights prepare on the worker. A repeated NLLB example still changes meaning. | 25 October local preparation section below; `.tools/local-translation-diagnosis/` |
| Whole-app CPU investigation | Kept Qwen prompt caching, repeated-translation caching, OpenMP wait changes and idle/music/log optimizations. Forced AVX-512 and MKL were rejected; earlier priority/GPU tradeoffs remain recorded below. | 26 October section below; `.tools/perf-2026-10-26/` |
| Hy-MT2 versus NLLB/Qwen candidates | Hy-MT2 Q4 was added as an optional translator after a 31-line comparison; Qwen2.5 3B was rejected. NLLB remains the default, not a claim about the user's saved selection. | [LOCAL_TRANSLATION_PLAN.md](LOCAL_TRANSLATION_PLAN.md), `.tools/model-candidates/results-*.json` |
| VR and compact UI work | Integrated wrist display, responsive resizing and compact model groups; native rendering/previews checked, live headset behavior outstanding. | [CHANGELOG.md](CHANGELOG.md), `.tools/vr-merge/`, `.tools/resize-ui/`, `.tools/model-list-ui/` |
| Gaming resource budget | One-thread inference, below-normal priority, guarded NLLB/Qwen CUDA, bounded speech work, model cleanup and idle UI changes implemented in `1efb598`. | 27 October section below; `.tools/gaming-validation/` |

External documentation research for the gaming pass was requested through `/agy` in the terminal, covering CTranslate2 CUDA/threads, faster-whisper host threads, OpenMP waits, ONNX/SenseVoice threading, llama.cpp and Windows priority. The recorded `agy` attempts timed out at two- and three-minute limits without a completed source-backed answer; auto mode also reported that it was unavailable for the account. Do not count these attempts as completed documentation verification. The implemented choices were checked through local code, installed runtime probes, regression tests and the measurements below. The local probe reported CTranslate2 4.8.2 with `int8_float16` support and a CPU-only llama.cpp runtime. Model-card/source links from earlier research remain in [LOCAL_TRANSLATION_PLAN.md](LOCAL_TRANSLATION_PLAN.md).

## 27 October: gaming CPU/GPU budget (source only)

A gaming pass measured local translation on the Ryzen 7 7800X3D / RTX 3080 10 GiB / 32 GB desktop with synthetic text, read-only installed weights and no VRChat/OSC/headset. It changes the defaults but is not a full game benchmark. The following totals cover three warm translations (EN→VI, ZH→EN, VI→ZH), after weight loading and one warm-up translation; loading is recorded separately in each JSON. Each mode was run once, so these are small component samples, not stable median/p95 estimates.

| NLLB, three short lines | Wall total | CPU total | Notes |
| --- | ---: | ---: | --- |
| CUDA `int8_float16` | 0.21 s | 0.20 s | about 1.1 GiB extra VRAM |
| CPU INT8, one thread | 1.74 s | 1.67 s | default CPU fallback budget |
| CPU INT8, two threads | 1.06 s | 1.92 s | `VRCT_CPU_THREADS=2` |

Hy-MT2 1.8B, the same three warm lines: one thread **4.55 s wall / 4.20 CPU-s**, two threads **2.50 s / 4.53 CPU-s**, with identical output between thread settings. One thread reduced total CPU work about 7% but increased wall time about 82%; its main benefit is using fewer cores at once. Hy-MT2 remains CPU-only and is not the default. GPU NLLB used about 89% less translation CPU time than two-thread CPU NLLB on these three lines; this is not an 89% whole-app or PC CPU reduction. NLLB output matched across all three modes here, but the earlier 26 October comparison changed 4 of 15 CUDA outputs, so equality is not guaranteed for every line.

Real lifecycle checks used installed NLLB and Qwen weights and the synthetic sentence "Please wait for me." (EN→VI). Both matched CPU/CUDA output, released GPU weights under injected low-memory telemetry, and loaded CPU on the next request; an immediate post-load reserve failure also completed on CPU. These checks simulated pressure rather than filling the GPU with a game. Their **load-plus-first-translation** wall times were Qwen CUDA 3.92 s / CPU 4.35 s and NLLB CUDA 1.55 s / CPU 1.74 s; they are not warm latency measurements and must not be compared directly with the three-line table.

Observed system free-VRAM decreases were approximately 1,100 MiB for NLLB and 2,250 MiB for Qwen (about 1.1 and 2.2 GiB), not isolated process-memory accounting. Readings after release within the same process remained roughly 150–260 MiB below the initial free-memory readings; native context retention and uncontrolled background use mean this is not proof of zero residual GPU memory. Production admission allows 1.5 GiB for NLLB or 3 GiB for Qwen, plus a 3 GiB reserve. Actual free memory is rechecked immediately after load, before subsequent inference at most once per 10 seconds, and while the local worker is idle. This is a sampled memory policy, not a continuous reservation or a GPU-utilization limit; it cannot guarantee game FPS. CUDA inference failure reports an error for that request and makes the next request use CPU; it does not silently retry that failed translation.

This pass also sets one inference thread by default, puts the process below normal priority on Windows and bounds speech queues. The earlier whole-app replay rejected below-normal priority because saturated translation throughput fell by about a third. The new default is a gaming-responsiveness choice, not a measured latency win; `VRCT_PROCESS_PRIORITY=normal` and `VRCT_CPU_THREADS=2` restore the earlier priority/thread choices without reverting queue or cleanup fixes. No fresh priority comparison, live game FPS, VRChat, headset or Windows 10 check was run. Evidence: `.tools/gaming-validation/`, `.tools/gaming-cpu1.json`, `.tools/gaming-cpu2.json`, `.tools/gaming-gpu.json`.

### Validation and retained evidence

The latest full suite against committed source passed **750 tests in 38.73 seconds**, with zero failures, errors or skips. The earlier inherited-state run passed 734 tests before the final regressions were added. Coverage includes queue overload/stale audio, shutdown cancellation without late chatbox sends, provider rechecks when Local Model is reselected, saved settings applied before hearing startup, GPU admission/post-load/idle checks, DLL handle lifetime, hidden Settings/wrist work and English/Chinese/Vietnamese completion notes. Fake clocks, telemetry and runtimes in the suite are separate from the real-model checks above. The handoff also records an isolated offscreen startup/shutdown check; it is not a live microphone or headset result.

| Evidence | Contents |
| --- | --- |
| `.tools/gaming-cpu-probe.py`, `.tools/gaming-cpu1.json`, `.tools/gaming-cpu2.json`, `.tools/gaming-gpu.json` | NLLB warm translations, separate load times, process CPU time and free VRAM readings |
| `.tools/gaming-validation/hy-mt-cpu.py`, `hy-mt-cpu1.json`, `hy-mt-cpu2.json` | Hy-MT2 one/two-thread warm translations and separate loading |
| `.tools/gaming-validation/cuda-lifecycle.py`, `cuda-lifecycle-translator.json`, `cuda-lifecycle-qwen_translator.json` | Real model load/inference, injected idle/post-load pressure, CPU fallback and release readings |
| `.tools/gaming-validation/final-tests.xml` | Latest 750-test suite, 27 October at 08:55 +07:00 |
| `.tools/gaming-resume-baseline.xml` | Initial 734-test suite |
| `.tools/gaming-validation/settings-before.json` | Pre-validation settings hashes; comparison after continuation confirmed unchanged UI, provider/model and VR settings |

Raw artifacts under `.tools/` are local and ignored by Git; the Markdown summaries travel with source exports. Earlier real-model probes read installed weights without modifying them. For future tests, follow current [AGENTS.md](AGENTS.md): isolate AppData and use fakes or independent workspace fixtures, not the user's model cache. No new binary, version bump, push or publication accompanies this source optimization or documentation update.

## 26 October: whole-app CPU and PC impact with local SenseVoice + Qwen (source only)

The user reported the PC lagging whenever ART is open. Saved setup: local SenseVoice hearing, local Qwen3 1.7B translation, **voice detector off**, subtitles from an Elgato loopback, wrist display on. Ryzen 7 7800X3D with SMT off (8 hardware threads); Discord, OBS and QQ were running. The real app (window, engine threads, wrist display) replayed a 167.6 s, 48 kHz track of 12 Chinese speech-over-music clips with music/noise gaps through a fake loopback device, using a copy of the saved settings without provider keys and a fake chatbox (no OSC). `psutil` sampled the process from outside; the first 25 s were excluded. A separate "game" probe ran fixed-work 90 FPS frame loops. Harness and raw results: `.tools/perf-2026-10-26/`.

**Where the time goes.** With the detector off, every 4 s of non-silent sound is transcribed and translated. SenseVoice took about 130 ms per piece; Qwen took 0.6–3.9 s on two threads per line, including junk lines such as "He." or "T.". Native model threads, mostly Qwen, used about 94% of the app's CPU. Qwen spends about 100 ms per generated token versus about 6 ms per prompt token. With continuous speech it cannot keep up with one piece every 4 s: translation delay grew to 15–21 s in the busiest part. The UI thread used about 1% of a core, with p99 timer lateness around 2 ms.

| Same replay, no other load | CPU, average cores of 8 | Lines | Median delay | Peak RAM |
| --- | ---: | ---: | ---: | ---: |
| Before (3 runs) | 0.93, 0.98, 0.99 | 29 | 4.5–7.6 s | 2.3 GB |
| After (final code, 2 runs) | 0.90, 0.94 | 29 | 5.7–6.5 s | 2.3 GB |
| After, detector on (Qwen) | 0.67 | 9 whole sentences | 8.9 s | 2.4 GB |
| After, NLLB instead of Qwen | 0.29 | 28 | 0.8 s | 1.2 GB |
| After, NLLB + detector on | 0.20 | 9 whole sentences | 2.9 s | 1.2 GB |

Translations were identical before and after. Qwen's native compute fell from 113 to 106 CPU-seconds per 125 s (−6%). Prefix caching alone measured −8.6% CPU over 45 isolated Qwen calls (−20% for short lines), with byte-identical output. Exact repeated lines now skip the local model; this replay had few repeats, while the user's log showed "T."/"I." repeatedly. The model choice and detector setting dominate: they are user choices and were not changed. NLLB/Qwen translation quality was not compared here; see LOCAL_TRANSLATION_PLAN.md.

**Rejected after measurement.** Below-normal process priority for model threads cut the app's translation throughput by about a third under a realistic load (10–11 lines instead of 16–18; 55–58 s median delay instead of 9–37 s) without a measurable probe improvement (23% missed frames versus 19–24%). It helped the probe only when the CPU was fully saturated, where translation was already unusable. CTranslate2's forced AVX-512 path was slightly slower and changed 7 of 15 Qwen outputs; Intel MKL was about 10 times slower on this AMD CPU and changed 8 of 15. The default backend is kept. **The 27 October gaming pass above later reintroduced below-normal process priority as a deliberate gaming tradeoff; it has an opt-out and was not re-benchmarked.**

**Music dialog.** After the Music dialog had been opened once, its 50 ms poll and 2 s VRChat-log check ran for the rest of the session. The log check re-read up to 8 MB and scanned it with a regex whenever VRChat wrote to its log: 61.9 ms per check on an 8 MB synthetic log (3.1% of a core, holding Python's lock). Reading only appended lines took 0.21 ms.

Limits: no live VRChat, headset or real QQ call; the probe is a stand-in for a game; Discord/OBS background varied between runs (DWM and probe numbers were noisy, so no game-FPS claim is made).

**Follow-up: the user switched to NLLB with the detector on.** Per sentence, the remaining delay was 0.8 s of intentional end-of-sentence quiet, 0.2–0.5 s of SenseVoice and 0.6–3.2 s of NLLB. Startup is one ~3 s burst of 1–1.4 cores while models load; the window appears at 0.65 s. CTranslate2's bundled Intel OpenMP kept worker threads spinning for 200 ms after each step. `KMP_BLOCKTIME=1` (set by `engine/__init__.py` unless already set) gave identical output on 14 sentences and the same speed (638 vs 649 ms median), with 15% less translation CPU. In the full replay, ART fell from 0.211/0.204 to 0.173/0.176 cores, with identical lines in all four runs and a 2.3–2.5 s median delay either way.

**GPU instead of CPU (RTX 3080, measured, not adopted at the time).** With a 90 FPS CUDA stand-in for the game:

| NLLB + detector on | ART CPU | Extra VRAM | Stand-in late frames | Median delay |
| --- | ---: | ---: | ---: | ---: |
| SenseVoice on CPU (current) | 0.21 cores | 0 | 11.3% | 2.7 s |
| Whisper turbo on GPU | 0.21 cores | +2.4 GB | 16.9% | 3.3 s |
| Whisper turbo + NLLB on GPU | 0.12 cores | +3.3 GB | 19.4% | 2.5 s |

GPU hearing saved no CPU, because audio preparation and decoding still run on the CPU. All-GPU saved about 1% of an 8-core CPU for 3.3 GB of VRAM, which VRChat needs in VR. In isolation, NLLB on CUDA took 52 ms instead of 266 ms per line, but changed 4 of 15 outputs (mixed, not clearly worse). At that measurement the app had no GPU translation option; the **27 October pass above** later added a reserve-gated CUDA option for NLLB/Qwen with automatic CPU fallback. The stand-in baseline varied (11–13% late frames) with OBS/browser GPU use.

## 25 October: two online translation destinations (0.12.11)

The 0.12.10 helper waited for each destination before starting the next. In 0.12.11, an online `ServiceChain` opts into at most **two simultaneous requests per utterance**, and the caller emits complete results as they finish. Panel destinations are scheduled before chatbox-only destinations; duplicate destinations still run once, and a matching source destination reuses the original immediately. Local translators retain their existing serialization and CPU budget. There is no model, prompt, beam, token-limit or silence-threshold change.

The production helper was compared with the committed helper at development `3fccca6`, using the same `ServiceChain`, configured custom-domain model (advertised as Qwen3.8-27B), HTTP transport and six synthetic EN/ZH/VI phrases, each translated into two other languages. Mode order alternated by phrase. Configuration was read into memory once and supplied to both modes; no user settings were written, no live audio was recorded and no OSC was sent. The model identifier does not verify the server's actual weights, runtime, cache or hardware.

The first sequential pair took 4,140 ms, including a 4,043 ms first request. Client initialization, connection setup and server startup were not separated. **Both modes for that first phrase are excluded** from the warm comparison below (five paired phrases, ten requests per mode):

| Warm measure | Sequential baseline | Parallel targets |
| --- | ---: | ---: |
| First complete subtitle, median | 90.5 ms | 93.2 ms |
| Both translations complete, median | 188.8 ms | 102.8 ms |
| Both complete, observed range | 175.5–196.7 ms | 94.4–115.8 ms |

Both-language completion took about **46% less time** in this small sample. First-result latency was similar. All 24 requests succeeded; the twelve paired target outputs were identical across modes, including the first phrase. This demonstrates preserved output on these inputs, not a general accuracy improvement. Remote caching and background load are uncontrolled. Measurements exclude audio capture, recognition, sentence-end detection, worker queues, Qt presentation and OSC pacing; they do not establish end-to-end latency, FPS improvement or AMD performance. No local-inference speedup is claimed.

Concurrency preserves individual failures, target display order and one final ordered microphone/chatbox message. Partial callbacks run on the calling worker, not HTTP threads. Client/chain creation is synchronized; an in-flight success cannot erase another target's rate-limit cooldown. With two speaker workers, one microphone worker and one typed worker, the current app can have at most eight target requests active across separate utterances. Request count per utterance is unchanged, but a server with strict concurrent-request limits may still throttle; existing cooldown/error handling applies. The shared HTTP client supports threads ([HTTPX API](https://www.python-httpx.org/api/)).

Evidence is retained in `.tools/latency-0.12.11/production.json`, `measure.py` and regression tests in `tests/test_translation_targets.py` / `tests/test_typing.py`. A Qt worker test holds the first language unfinished and verifies that the second appears in its correct row while chatbox sending waits. A separate test covers a slow failure, original reuse, deduplication and independent partial success.

### Finding the cause of delay or wrong wording

`engine.log` now records `hearing source=... wait_ms=... recognition_ms=...`, per-target `translation target=... duration_ms=...`, and per-line translation duration alongside existing total latency. `wait_ms` includes the final quiet interval and hearing queue wait; it is not pure recognition time. Translation duration includes provider/model waiting and any existing fallback/retry. Timing lines add no transcript, URL or key.

- If the original transcript is wrong, investigate the audio source, overlapping voices/music, clipping, segmentation, language support and hearing model first. A translator cannot reliably reconstruct words that were lost.
- If the original is correct but its translation is wrong, investigate the selected translator, language direction, context and names/slang. Local versus online is not itself a quality guarantee; the specific model and decoding matter.
- Reducing unnecessary waiting does not require sacrificing accuracy. Shortening sentence pauses, reducing decoding quality or switching to a smaller model can create a different tradeoff; none is part of this change.
- Hearing and Translating are independent selections. SenseVoice's input languages do not include Vietnamese; choosing Vietnamese as a translation output does not add Vietnamese speech recognition.

No failing live utterance was supplied for this task, so the user's specific accuracy problem is not yet attributed to a proven cause.

## 25 October: local weight preparation and mixed-text correctness (0.12.12)

Installed NLLB/Qwen weights now load on the existing background translation worker during startup, under the same model lock used by later speech and typed calls. No dummy generation is performed. Missing weights are skipped; preparation failures are logged and can retry on the first translation. This moves loading earlier when there is enough startup time; it does not remove loading cost, guarantee that the first request will never wait, or change steady-state inference speed. Switching models later still loads lazily.

The other terminal replayed supplied text through real local NLLB with fake hearing and Qt rendering. Weight preparation took 1,225 ms. Three mixed CJK/English inputs previously copied unchanged because their source label matched English now reached NLLB in 199–287 ms. For example, the Chinese thank-you followed by “see you later” became “Thank you, see you later.” Ordinary English still reused the original with no inference. The pipeline and visible same-label translation checks passed. The fix adds necessary translation work for these previously skipped cases; it is a correctness fix, not a latency reduction.

A repeated Chinese negative phrase still became “I'm not going to say anything.” in both old and new paths. This is a demonstrated model meaning error; it has not been repaired by the scheduling or mixed-text fixes. No live audio accuracy conclusion follows from this replay. Evidence: `.tools/local-translation-diagnosis/verification.json` and `mixed-text-panel.png`; 559 source tests and a subsequent 170-test UI/local/target check passed.

## Earlier component measurements

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

PhoWhisper Small CPU INT8/two threads (one by default after the 27 October gaming pass) loaded and warmed in 4,877 ms. Two Vietnamese recordings matched reference words, ignoring case. Forced Vietnamese decoding took 2,428 and 2,081 ms; Auto took 4,209 and 3,621 ms. This supports offering PhoWhisper as a Vietnamese CPU specialist, not claiming it is faster than GPU Whisper turbo or validated for mixed speech.

Exact revisions/download hashes are in `engine/assets/local_models.json`; attribution and limits are in [LOCAL_TRANSLATION_PLAN.md](LOCAL_TRANSLATION_PLAN.md). Ignored local evidence: `.tools/model-additions/comparison.json`, `pho-smoke.json`, `qwen-1.7-smoke.json`. The new weights and existing benchmark recordings are not included in source exports or the EXE.
