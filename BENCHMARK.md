# Benchmark

Before the program was built, the candidate speech and translation models were measured on the same recordings in English, Chinese and Vietnamese, in two situations: **your own microphone** and **other players heard through VRChat**, with world music behind their voices.

This is a historical evaluation, not the current provider configuration. Version 0.11.5 supports six conversation languages, including Japanese and Korean; the measurements below do not benchmark those added languages. Choose current hearing and translation models in Settings → Models.

Everything here was measured on 2 October 2026 on one PC (Ryzen 7 7800X3D, RTX 3080 10 GB, Windows 11, internet from Vietnam). "Cloud" means the same open model run by an online service instead of this PC.

## The setup evaluated, and how it scored

| Step | Evaluated model or component | Score |
|---|---|---|
| Finding sentences | Silero voice detector, strictness 70% | blocked 14 of 14 clips without speech; passed 99% of sentences with music |
| Hearing | Whisper large-v3-turbo, online | 94.5% / 96.3% / 93.6% heard right (English / Chinese / Vietnamese, clean mic) |
| Hearing over loud music | same | 92.9% / 90.5% / 87.7% |
| Translating | `qwen3.8-27b`, then `gpt-oss-120b`, then `gpt-oss-20b`, online | 78–79% blind grade for the first two; 0.14 s per line |
| Speed, hearing | | 0.30 s per sentence |
| Speed, live in VRChat | | a translated line 1.2–2.2 s after the speaker stops |

Whisper large-v3-turbo was also evaluated on the local GPU: 0.57 s per sentence with VRChat running and 2.4 GB of GPU memory; accuracy is listed below. Current source and packaged editions include Local Model support, with model data downloaded separately.

## How it was measured

**Recordings.** [FLEURS](https://huggingface.co/datasets/google/fleurs) (Google, CC-BY 4.0), where the same sentences are read aloud in every language. One sentence therefore gives the correct text *and* the correct translation into the other languages. 40 sentences × 3 languages, each in 4 versions:

| Version | What it stands for |
|---|---|
| `mic` | the clean recording: your own microphone |
| `spk_voice` | the voice through Opus at 24 kbps: another player, world sound off |
| `spk_music10` | the same with music behind it, voice 10 dB louder than the music |
| `spk_music3` | the same with loud music, voice only 3 dB louder |

Plus 14 clips with **no speech at all** (four music tracks and hiss) to catch made-up text.

**Heard right** = 100% minus the error rate (wrong, missing and extra words; characters for Chinese). Punctuation, capital letters and traditional/simplified characters do not count as differences.

**Language.** On `mic` clips the engine is told the language (the program knows what you speak). On speaker clips it has to find the language itself.

## Hearing: nine engines

Heard right, in % (English / Chinese / Vietnamese).

| Engine | Clean mic | Voice only | Music | Loud music |
|---|---|---|---|---|
| Qwen3-ASR 1.7B (local) | 95.2 / 97.3 / 95.6 | 95.1 / 97.3 / 96.0 | 94.4 / 97.3 / 94.3 | 94.1 / 91.0 / 93.0 |
| Qwen3-ASR 0.6B (local) | 95.1 / 96.5 / 94.3 | 95.1 / 96.6 / 94.5 | 94.5 / 96.2 / 92.3 | 93.5 / 96.5 / 89.4 |
| Whisper large-v3 (local) | 95.1 / 95.8 / 93.5 | 94.8 / 95.1 / 92.5 | 94.4 / 95.8 / 91.8 | 93.6 / 95.0 / 89.5 |
| **Whisper large-v3-turbo (local)** | 94.6 / 96.0 / 93.7 | 94.5 / 95.8 / 92.2 | 92.9 / 94.6 / 91.7 | 93.5 / 92.7 / 86.6 |
| **Whisper large-v3-turbo (cloud)** | 94.5 / 96.3 / 93.6 | 94.2 / 95.8 / 92.7 | 91.0 / 90.8 / 91.7 | 92.9 / 90.5 / 87.7 |
| Whisper large-v3 (cloud) | 94.5 / 95.0 / 92.9 | 94.5 / 95.1 / 92.3 | 93.6 / 95.2 / 91.5 | 92.5 / 94.7 / 87.9 |
| SenseVoice small (local) | 93.2 / 94.6 / – | 92.6 / 94.3 / – | 91.5 / 94.1 / – | 89.0 / 93.1 / – |
| Gemini 3.5 Flash-Lite, listening ¹ | 94.0 / 92.0 / 94.2 | not run | 89.5 / 83.7 / 91.5 | not run |
| Gemini 3.5 Transcribe ² | 97.4 / – / – | not run | 94.1 / – / – | not run |

¹ 20 sentences instead of 40, to stay inside its free daily limit. ² English only: on the free tier it stalled after 40 clips. SenseVoice has no Vietnamese.

Speed, memory and behaviour:

| Engine | Seconds per sentence | GPU memory | Found the language (music) | Text on 14 no-speech clips |
|---|---|---|---|---|
| Qwen3-ASR 1.7B (local) | 0.87 | 4.8 GB | 93% | 3 |
| Qwen3-ASR 0.6B (local) | 1.22 | 2.1 GB | 100% | 3 |
| Whisper large-v3 (local) | 1.17 | 4.1 GB | 100% | 14 |
| **Whisper large-v3-turbo (local)** | 0.57 | 2.4 GB | 100% | 14 |
| **Whisper large-v3-turbo (cloud)** | 0.30 | none | 100% | 8 |
| Whisper large-v3 (cloud) | 0.43 | none | 100% | 4 |
| SenseVoice small (local) | 0.10 | 1.2 GB | 100% | 5 |
| Gemini 3.5 Flash-Lite, listening | 1.24 | none | – | 2 |

Local speeds were timed on the same 30 clips **while VRChat was running** on the same GPU, which is how the program is used. Without the game, Whisper large-v3-turbo needed 0.31 s.

What this decided:

- **The top engines are within about 2 points of each other**, which is too little to tell apart with 40 sentences per language. Speed, memory and limits decided instead.
- **Whisper large-v3-turbo** is the fastest engine that covers all three languages and fits beside a game (2.4 GB), and online services run the same model with no GPU use at all.
- **Qwen3-ASR 1.7B** had the highest numbers but needs 4.8 GB next to the game and sometimes guessed the wrong language.
- Without a voice detector, Whisper wrote text on **every** clip that had no speech ("Thank you.", "We'll be right back."). A voice detector is not optional.

## Voice detector

Silero VAD on all 494 clips, at three strictness settings.

| Strictness | Sentences passed (mic / voice / music / loud music) | No-speech clips blocked |
|---|---|---|
| 30% | 100% / 100% / 100% / 100% | 79% (11 of 14) |
| 50% (Silero's default) | 100% / 100% / 100% / 100% | 86% (12 of 14) |
| **70% (the program's default for game sound)** | 100% / 100% / 99% / 99% | **100% (14 of 14)** |

One thing it cannot do: sung lyrics count as a voice, so a world that plays songs can still produce lyric lines.

## From voice to translation

The first 20 sentences in the four directions that matter most (Chinese → English, Chinese → Vietnamese, English → Chinese, Vietnamese → Chinese). Each hearing engine's text was translated by the same translator (Gemini 3.5 Flash-Lite), so the table shows what hearing mistakes cost.

- **chrF**: an automatic score against the reference translation, higher is better.
- **Blind grade**: 24 answers per setup from the clips with music, graded 0–3 for meaning with the setup names hidden, by Claude (an AI model), then expressed in %.

| Hearing engine | chrF, clean mic | chrF, music | Blind grade |
|---|---|---|---|
| The correct text (upper limit) | 45.7 | 45.7 | 96% |
| Qwen3-ASR 1.7B | 44.2 | 43.5 | 90% |
| **Whisper large-v3-turbo** | 42.8 | 42.5 | 90% |
| Qwen3-ASR 0.6B | 42.6 | 41.5 | 85% |
| Whisper large-v3 (cloud) | 41.8 | 42.4 | 86% |
| One model hears *and* translates in one step ³ | 24.6 | 16.3 | 18% |

³ Gemini 3.5 Flash-Lite given the sound and asked for the translation. It often wrote the sentence down in the original language, mixed two languages, or answered "nobody speaks" over music. **Hearing first, then translating the text, is far better.**

## Translators

Input: what Whisper large-v3-turbo heard, the same 20 sentences and four directions, one request per sentence as in the program.

| Translator | chrF, clean mic | chrF, music | Blind grade | Seconds per line | Free requests a day |
|---|---|---|---|---|---|
| Gemini 3.5 Flash-Lite ⁴ | 42.8 | 42.5 | 90% | about 0.7 | 500 |
| **`qwen3.8-27b` (cloud)** | 42.9 | 42.8 | 78% | 0.14 | 1,000 |
| **`gpt-oss-120b` (cloud)** | 42.2 | 41.7 | 79% | 0.49 | 1,000 |
| **`gpt-oss-20b` (cloud)** | 41.0 | 40.8 | 72% | 0.37 | 1,000 |

⁴ Asked ten lines per request, the others one line per request, so the gap may be a little smaller in real use. It was the best at repairing misheard words (a misheard "联合股" back to "United Nations"), but its free tier allows 500 lines a day, which live voice chat passes within about an hour. With your own key it is one of the choices in Settings → Models.

They are tried in the order above; when one reaches its limit, the next one answers.

## Cantonese

Whisper understands Cantonese but calls it "Chinese": its language guess gave Cantonese a probability of 0.000 on every clip, Cantonese and Mandarin alike. Picking **Cantonese** under "They speak" puts it in Cantonese mode.

| Test | Result |
|---|---|
| 20 Hong Kong recordings of formal sentences (FLEURS `yue_hant_hk`) | 92.0% of characters heard right clean, 88.5% with music (Mandarin: 96%) |
| Their English translations (12 checked) | chrF 48.4 (Mandarin → English: 57–62); 9 of 12 right in meaning |
| 8 everyday Cantonese sentences (computer voices) | all translated into English; 1 shifted in meaning |

Three detectors were tried for telling the two apart automatically:

| Detector | Cantonese clips labelled Cantonese | Mandarin clips labelled Cantonese |
|---|---|---|
| Whisper large-v3-turbo | 0 of 28 | 0 of 40 |
| Whisper large-v3 (cloud) | 0 of 12 | 0 of 12 |
| SenseVoice small (language tag only) | 28 of 28 | 0 of 40 |

## Live

First run in a real Chinese VRChat room (28 minutes, about 320 lines, online hearing): other players' Mandarin and English were heard and translated as they spoke, with the translated line appearing **1.2–2.2 s after each person stopped talking**. About 0.8 s of that is the wait to be sure the sentence is over.

## Limits of this benchmark

- FLEURS is **read** speech: clear, formal sentences. Real players have accents, cheap microphones and talk over each other. Only the live run above covers that, and it was not scored.
- The music and the voice compression are **simulated** (Opus 24 kbps is an assumption; VRChat does not publish its bitrate).
- 40 sentences per language: differences under about 2 points are noise.
- The blind grades were given by an AI model, on 24 answers per setup. One answer is worth about 4 points.
- Speeds are from one PC and one internet connection.
- Cloud services change their free limits without notice.

## Your own key: what the benchmark says

Settings → Models also takes your own key for an online service. From the tables above:

- **Hearing**: Qwen3-ASR heard best (its open 1.7B version; Qwen's online service and OpenRouter run it), and Qwen's service also tells Cantonese from Mandarin. Whisper (OpenAI, OpenRouter, or any Whisper server) is the proven choice.
- **Translating**: Gemini Flash-Lite had the best blind grade (90%).
- **Not recommended**: one model hearing *and* translating in one step (18%).
