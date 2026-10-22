# Local translation model plan

Saved 2026-10-22 at the user's request. Scope: text translation after speech recognition, running on the user's PC. Speech-recognition and text-to-speech model variants are separate tasks.

## Decision rule

**Low latency first; other models remain alternatives.** Choose the lowest measured delay among models that preserve meaning, retain every sentence, use the requested language and avoid repeated or explanatory output. Keep the existing translator available while comparing candidates. A smaller model or faster token rate does not automatically produce a usable complete translation sooner.

Translation must work offline after setup. Download accessibility from China is a requirement for installation: prefer verified ModelScope files or a transferable offline package, with pinned revisions and hashes. No mainland-China connection has been tested. Download size is not runtime RAM/VRAM usage.

## Shortlist and proposed evaluation order

This is an order for experiments, **not a measured speed ranking**. No Qwen or Hy-MT model has been benchmarked on this PC or integrated into ART's Local Model list.

| Candidate | Role in the comparison | Format and implementation considerations |
| --- | --- | --- |
| Existing NLLB-200 distilled 600M / CTranslate2 INT8 | Measure the current baseline first; retain it as a fallback. | Already integrated on CPU. The optional offline package solves its Hugging Face installation dependency. Do not assume a decoder-only LLM will beat this encoder-decoder model. |
| Qwen3-0.6B, non-thinking | First small Qwen candidate to test for low latency. Translation accuracy, omissions and all six app languages need evaluation. | Official GGUF repository currently lists Q8_0, approximately 639 MB. The official ModelScope listing was checked. Do not advertise a verified official Q4_K_M file: none was listed in that repository during this check. A separately verified Q4 conversion can be evaluated later. [Model card](https://huggingface.co/Qwen/Qwen3-0.6B), [GGUF files](https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/tree/main), [ModelScope](https://modelscope.cn/models/Qwen/Qwen3-0.6B-GGUF). |
| Qwen3.5-0.8B, non-thinking | Another small-model comparison; test whether it improves usable translation within the latency budget. | Its official card says non-thinking is the default. It also supports vision, which ART does not need for text translation. Confirm support in the chosen Windows runtime and verify a suitable converted file before integration; the checked ModelScope page is the base model, not a verified GGUF artifact. [Model card](https://huggingface.co/Qwen/Qwen3.5-0.8B), [ModelScope](https://modelscope.cn/models/Qwen/Qwen3.5-0.8B). |
| Tencent Hy-MT2-1.8B Q4_K_M | Translation-specialized alternative to compare when the small Qwen models miss meaning or languages. It may still win overall latency after failed outputs/retries are counted. | Official GGUF is approximately 1.13 GB. Tencent lists English, Chinese, Cantonese, Vietnamese, Japanese and Korean. The ModelScope file listing and a 1 KiB range download from its CDN were verified. Needs a GGUF-capable runtime rather than the current NLLB adapter. [Model card](https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF), [ModelScope](https://modelscope.cn/models/Tencent-Hunyuan/Hy-MT2-1.8B-GGUF). |
| Qwen3-1.7B or Qwen3.5-2B, non-thinking | Optional larger Qwen comparison if the smaller candidates fail quality checks. Do not make either the default without measured benefit. | More parameters do not establish the actual delay or quality on this PC. Qwen3 requires thinking to be explicitly disabled; Qwen3.5-2B documents non-thinking as its default. [Qwen3-1.7B](https://huggingface.co/Qwen/Qwen3-1.7B), [Qwen3.5-2B](https://huggingface.co/Qwen/Qwen3.5-2B). |
| M2M100-418M | Lower-priority encoder-decoder alternative if the GGUF candidates do not meet the latency target. | Its published language list includes English, Chinese, Vietnamese, Japanese and Korean, but no separate Cantonese target. It needs conversion/tokenizer and adapter work; it is not a full replacement for ART's six-language selection. No compatible China-hosted artifact or ART benchmark has been verified. [Model card and language list](https://huggingface.co/facebook/m2m100_418M). |

The original Hy-MT recommendation was a translation-focused candidate. The user's latency-first preference means it is a comparison option, not an already chosen default. General instruction-following benchmarks do not establish translation quality for VRChat speech.

## Settings and integration to evaluate

- For Qwen3, disable thinking in the actual chat template/runtime (`enable_thinking=False` where supported). Removing reasoning text after generation does not save its generation time. Qwen3.5 does not officially support Qwen3's textual thinking switches; verify its non-thinking template instead. See the linked Qwen model cards.
- Use text-only, translation-only prompts and validate model-specific decoding settings. Do not copy one model's temperature or repetition settings into every other model without testing.
- Keep the model loaded between utterances, prewarm it before live capture, and measure startup separately. Use a short context and a bounded output allowance that still fits the complete translation. Reject truncated output instead of presenting it as successful.
- A localhost inference server is still fully local and can be evaluated through ART's Custom domain path. That path needs prompt/template, model-list and error-handling checks; it is not a claim that these candidates already work correctly in ART. The desired integrated experience remains Download → Use model in Local Model setup.
- Check CPU-only operation first, then optional GPU offload with VRChat and the chosen speech recognizer running. A GPU speedup in isolation may disappear under shared load. Preserve the current app behavior during evaluation.
- Select one active translator. Do not run every candidate or a second quality pass for every utterance; extra work and fallback delays count against latency.

## Measurements needed before choosing a default

1. Replay the same short conversational texts through each candidate: ordinary sentences, two-sentence messages, names, numbers, negation, VRChat terms, mixed languages, and stuttered recognition. Include the earlier repetition and missing-VR-sentence failures. Use material approved for testing.
2. Cover all six app languages, with particular attention to English/Chinese/Vietnamese and Cantonese. Have language-competent reviewers check meaning, sentence completeness and target language; do not infer quality solely from language-count claims.
3. Record cold startup separately from warm translation. For warm requests, measure median and p95 time from recognized text being ready to the first usable displayed translation and to the complete translation. Also count errors, omissions, repetition, retries and wrong-language results. First-token latency alone is insufficient.
4. Repeat the comparison with VRChat and live recognition sharing the PC. Record CPU, RAM, VRAM and impact on the game. Check one output language and three output languages separately; measure full speech-to-subtitle delay as well as translation-only time.
5. Record the exact model revision, file hash, quantization, runtime version, prompt, generation settings, thread counts and GPU offload. Set the acceptable latency/quality thresholds from the baseline and user experience before choosing a winner. No target milliseconds or performance results are invented here.

## Current status

- Saved preference and shortlist only; no new inference runtime installed, no model downloaded for these comparisons, and no default changed in this task.
- NLLB is the implemented local translator. Its offline installer was previously tested with actual model files and published with v0.12.3.
- Qwen and Hy-MT performance, mainland-China connectivity, runtime integration and translation quality remain to be tested.
- Speaker identification remains deferred as recorded in [ROADMAP.md](ROADMAP.md).
