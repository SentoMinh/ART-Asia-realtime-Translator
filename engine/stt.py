"""Speech to text: one sentence of 16 kHz sound in, text and its language out.

Two kinds of engine with the same interface, picked in Settings → Models:
  LocalWhisper   Whisper large-v3-turbo on this PC's GPU (2.4 GB of GPU memory, no limits)
  CloudHearing   an online service (engine/services.py): the developer's relay, OpenAI,
                 Gemini, Qwen, OpenRouter, or any OpenAI-compatible address
In the benchmark Whisper heard 94-96% right on a clean mic and 87-96% with music behind the voice.

Language focus. With a language given, the model is held to it. Without one ("They speak:
Auto-detect") the engines focus on the program's own languages: a language outside them is
believed only when the model is at least 80% sure. Otherwise the sentence is taken as the main
language that fits best. That stops noise and half-heard words from turning into Spanish or
Japanese lines in a Chinese room.
"""
from __future__ import annotations

import base64
import importlib.util
import io
import json
import math
import os
import time
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import services

RATE = 16000
MAIN_LANGS = ("en", "zh", "yue", "vi")      # yue = Cantonese, which Whisper tells apart from Mandarin
CHINESE = ("zh", "yue")
SURE = 0.8                # a language outside MAIN_LANGS is only believed at this certainty
ASK_AGAIN = ("en", "zh", "vi")              # what is asked again in; Cantonese goes with zh
LANGUAGE_NAMES = {"english": "en", "chinese": "zh", "mandarin": "zh", "cantonese": "yue",
              "yue chinese": "yue", "vietnamese": "vi", "japanese": "ja", "korean": "ko",
              "spanish": "es", "french": "fr", "german": "de", "russian": "ru", "thai": "th",
              "indonesian": "id", "portuguese": "pt", "italian": "it", "arabic": "ar",
              "hindi": "hi", "malay": "ms", "tagalog": "tl", "turkish": "tr", "dutch": "nl",
              "polish": "pl", "ukrainian": "uk"}
BELIEVED_S = 60.0         # a language believed this recently is accepted again without asking
PHANTOMS = ("hãy subscribe cho kênh", "ghiền mì gõ", "đừng quên đăng ký kênh",
            "cảm ơn các bạn đã theo dõi", "thanks for watching", "thank you for watching",
            "please subscribe", "subtitles by", "amara.org",
            "请不吝点赞", "明镜与点点", "字幕由", "字幕by", "谢谢观看", "感谢观看", "謝謝觀看",
            "ご視聴ありがとうございました", "시청해 주셔서 감사합니다")
# Languages with a script of their own: text claimed to be in one must be written in it.
SCRIPTS = {"ja": ((0x3040, 0x30FF),), "ko": ((0xAC00, 0xD7AF), (0x1100, 0x11FF)),
           "ru": ((0x0400, 0x04FF),), "uk": ((0x0400, 0x04FF),), "th": ((0x0E00, 0x0E7F),),
           "ar": ((0x0600, 0x06FF),), "hi": ((0x0900, 0x097F),)}
# Words only Cantonese writes. Whisper can't tell Cantonese from Mandarin by sound (it calls
# both "zh", and usually writes Cantonese speech as standard Chinese), but when it does keep
# these, the speaker is Cantonese.
CANTONESE_MARKS = set("嘅咗唔冇喺佢哋嚟啲嗰噉乜嘢睇攞揾搵諗瞓㗎喎啩")


class SttError(Exception):
    """No text right now; the message says why in plain words."""


@dataclass
class Heard:
    text: str = ""
    lang: str = ""            # "en", "zh", "yue", "vi", or another code Whisper found


def looks_cantonese(text: str) -> bool:
    return sum(ch in CANTONESE_MARKS for ch in text) >= 2


def in_own_script(text: str, lang: str) -> bool:
    """False when `lang` has a script of its own and under half of the letters are in it.
    Languages written in Latin letters can't be checked this way and pass."""
    ranges = SCRIPTS.get(lang)
    letters = [ch for ch in text if ch.isalpha()]
    if not ranges or not letters:
        return True
    own = sum(any(low <= ord(ch) <= high for low, high in ranges) for ch in letters)
    return own * 2 >= len(letters)


HAN = ((0x4E00, 0x9FFF), (0x3400, 0x4DBF), (0xF900, 0xFAFF))
KANA = ((0x3040, 0x30FF),)
VIETNAMESE = set("ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ")


def guess_language(text: str) -> str:
    """The language from the writing alone, for services that don't say which one they heard.
    Latin letters can only be told apart for Vietnamese (its own marks); the rest is English."""
    letters = [ch for ch in text.lower() if ch.isalpha()]
    if not letters:
        return ""

    def share(ranges) -> float:
        return sum(any(low <= ord(ch) <= high for low, high in ranges) for ch in letters) / len(letters)
    if share(KANA) > 0.1:
        return "ja"
    if share(HAN) >= 0.5:
        return "yue" if looks_cantonese(text) else "zh"
    for lang in ("ko", "ru", "th", "ar", "hi"):
        if share(SCRIPTS[lang]) >= 0.5:
            return lang
    return "vi" if sum(ch in VIETNAMESE for ch in letters) * 20 >= len(letters) else "en"


def mostly_chinese(text: str) -> bool:
    """At least half of the letters are Chinese characters."""
    letters = [ch for ch in text if ch.isalpha()]
    return bool(letters) and sum(any(low <= ord(ch) <= high for low, high in HAN) for ch in letters) * 2 >= len(letters)


def language_code(found: str, text: str) -> str:
    """A service's language answer ("chinese", "zh", "Cantonese", "") as a code."""
    found = found.strip().lower()
    if found in LANGUAGE_NAMES:
        return LANGUAGE_NAMES[found]
    if 2 <= len(found) <= 3 and found.isalpha():
        return found
    return guess_language(text)


def is_phantom(text: str) -> bool:
    """Lines Whisper is known to make up over music or unclear sound: video sign-offs it
    saw too often in training."""
    plain = " ".join(text.lower().split())
    return any(phrase in plain for phrase in PHANTOMS)


def tidy(text: str, lang: str) -> Heard:
    """Drops known made-up lines. Whisper writes Chinese in traditional or simplified
    characters at random: Mandarin is shown simplified, Cantonese the Hong Kong way
    (traditional)."""
    if is_phantom(text):
        return Heard("", lang)
    if lang == "zh" and looks_cantonese(text):
        lang = "yue"
    if lang not in CHINESE:
        return Heard(text, lang)
    try:
        import zhconv
    except ImportError:
        return Heard(text, lang)
    return Heard(zhconv.convert(text, "zh-cn" if lang == "zh" else "zh-hk"), lang)


def _add_gpu_libraries() -> None:
    """faster-whisper needs NVIDIA's cuBLAS and cuDNN. They come from the pip packages
    nvidia-cublas-cu12 / nvidia-cudnn-cu12, or from PyTorch if that is installed."""
    folders = []
    for package, sub in (("nvidia.cublas", "bin"), ("nvidia.cudnn", "bin"), ("torch", "lib")):
        try:
            spec = importlib.util.find_spec(package)
        except (ImportError, ValueError):
            spec = None
        for location in (spec.submodule_search_locations or []) if spec else []:
            folder = Path(location) / sub
            if folder.is_dir():
                folders.append(str(folder))
    for folder in folders:
        os.add_dll_directory(folder)
    if folders:       # cuDNN loads its parts by name later, which only looks at PATH
        os.environ["PATH"] = os.pathsep.join(folders + [os.environ.get("PATH", "")])


class LocalWhisper:
    name = "local"

    def __init__(self, model: str = "large-v3-turbo"):
        self._model_id = model
        self._model = None

    def load(self) -> None:
        if self._model is not None:
            return
        if importlib.util.find_spec("faster_whisper") is None:
            # the downloadable program leaves the local model out (it needs 2 GB of GPU libraries)
            raise SttError("this download has no Local Model: choose an online service in "
                           "Settings → Models (the source version adds it)")
        try:
            _add_gpu_libraries()
            import huggingface_hub.file_download as download
            # Without Windows developer mode the model cache can't use file links, and the
            # library's own check for that is not thread-safe: always copy instead.
            download.are_symlinks_supported = lambda cache_dir=None: False
            from faster_whisper import WhisperModel
            model = WhisperModel(self._model_id, device="cuda", compute_type="float16")
            # the first run on a GPU is slow (2 s instead of 0.6 s): spend it on silence now
            list(model.transcribe(np.zeros(RATE, dtype="float32"), language="en", beam_size=1)[0])
            self._model = model
        except Exception as error:
            raise SttError(f"the speech model could not be loaded: {error}") from error

    def transcribe(self, samples: np.ndarray, lang: str | None, prefer: tuple = ()) -> Heard:
        """`prefer` is not needed here: the model says how likely each language is."""
        self.load()
        try:
            if lang == "zh":
                # "Chinese" means Mandarin or Cantonese: let the model tell which one it hears
                text, info = self._run(samples, None)
                if info.language not in CHINESE:
                    text, info = self._run(samples, "zh")
            else:
                text, info = self._run(samples, lang)
            if lang is None and info.language not in MAIN_LANGS and info.language_probability < SURE:
                # under 80% sure of a language that isn't ours: it is one of ours, heard badly
                best = max(MAIN_LANGS, key=lambda code: dict(info.all_language_probs or []).get(code, 0))
                text, info = self._run(samples, best)
        except SttError:
            raise
        except Exception as error:
            raise SttError(f"the speech model failed: {error}") from error
        return tidy(text, info.language)

    def _run(self, samples: np.ndarray, lang: str | None):
        segments, info = self._model.transcribe(
            samples, language=lang, beam_size=5, condition_on_previous_text=False,
            without_timestamps=True)
        # Whisper's own signs of made-up text: "probably no speech" or repeating itself
        kept = [s.text for s in segments
                if not (s.no_speech_prob > 0.6 and s.avg_logprob < -1.0) and s.compression_ratio <= 2.6]
        return "".join(kept).strip(), info


def wav_bytes(samples: np.ndarray) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes((np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes())
    return out.getvalue()


HEAR_PROMPT = (
    "Write down exactly what is said in the recording, in the language it is spoken in; never "
    "translate. Write Cantonese as spoken Cantonese. If nobody speaks, or there is only music or "
    "noise, the text is empty. Answer with JSON only: "
    '{"language": "<ISO 639-1 code; yue for Cantonese>", "text": "<the words>"}')


class CloudHearing:
    """Hearing through an online service, chosen by its id in engine/services.py. The address,
    key and model are read again for every sentence, so a change in Settings works at once."""

    def __init__(self, service: str = "dev", http=None, clock=time.monotonic):
        self.name = service
        self._http = http
        self._clock = clock
        self._wait_until = 0.0
        self._believed = ("", 0.0)     # the language outside ours believed last, and when
        self._plain: set[str] = set()  # models that refused the service's extra fields

    def available(self) -> bool:
        return services.ready(self.name)

    def missing(self) -> str:
        return services.missing(self.name)

    def load(self) -> None:
        problem = services.missing(self.name)
        if problem:
            raise SttError(problem)
        if self._http is None:
            import httpx
            self._http = httpx.Client(timeout=20)

    def transcribe(self, samples: np.ndarray, lang: str | None, prefer: tuple = ()) -> Heard:
        """`prefer`: the main languages most likely here (heard last, the user's own), tried
        first when an unsure guess at another language has to be asked again."""
        self.load()
        if lang == "zh":
            # "Chinese" means Mandarin or Cantonese: ask without a language, and only insist
            # on Mandarin if the service heard something else entirely
            heard, _ = self._ask(samples, None)
            return heard if heard.lang in CHINESE else self._ask(samples, "zh")[0]
        if lang is not None:
            return self._ask(samples, lang)[0]
        heard, certainty = self._ask(samples, None)
        if not heard.text or heard.lang in MAIN_LANGS:
            return heard
        if certainty is None:
            # this service gives no certainty: its language is taken when the words are
            # written in that language's own script
            if in_own_script(heard.text, heard.lang):
                return heard
            return tidy(heard.text, guess_language(heard.text))
        # Whisper gives no probability for its language guess. What it does give is how
        # certain the model was of the words it wrote. So a language that isn't ours is
        # believed when
        # - its words are in its own script (Korean in Hangul, Russian in Cyrillic...), and
        # - that certainty is at least 80%, or it was believed within the last minute, or
        #   it beats the same sentence asked again as each of our languages.
        if not in_own_script(heard.text, heard.lang):
            certainty = 0.0
        lately = heard.lang == self._believed[0] and self._clock() - self._believed[1] < BELIEVED_S
        if certainty >= SURE or (lately and certainty > 0):
            self._believed = (heard.lang, self._clock())
            return heard
        best = (heard, certainty)
        for code in dict.fromkeys(c if c != "yue" else "zh" for c in (*prefer, *ASK_AGAIN)):
            if code not in ASK_AGAIN:
                continue
            answer = self._ask(samples, code)
            if answer[0].text and (answer[1] or 0.0) > best[1]:
                best = (answer[0], answer[1] or 0.0)
                if best[1] >= SURE:
                    break
        if best[1] <= 0:
            return Heard("", heard.lang)      # nothing believable either way: show nothing
        if best[0].lang not in MAIN_LANGS:
            self._believed = (best[0].lang, self._clock())
        return best[0]

    def _ask(self, samples: np.ndarray, lang: str | None) -> tuple[Heard, float | None]:
        """The answer, and how certain the model was of its words (0.0 – 1.0), or None when
        the service doesn't say."""
        title = services.title(self.name)
        if self._clock() < self._wait_until:
            raise SttError(f"{title} is at its limit; waiting for it to refill")
        model = services.setting(self.name, "hear_model")
        if not model:
            raise SttError(f"{title} has no hearing model yet (Settings → Models)")
        style = services.SERVICES[self.name].hear_style if self.name in services.SERVICES else "whisper"
        url = services.setting(self.name, "url").rstrip("/")
        sound = wav_bytes(samples)
        try:
            if style == "whisper":
                data = {"model": model, "temperature": "0",
                        "response_format": "verbose_json" if self._detailed(model) else "json"}
                if lang:
                    data["language"] = lang
                answer = self._http.post(f"{url}/audio/transcriptions", data=data,
                                         headers=services.auth(self.name),
                                         files={"file": ("speech.wav", sound, "audio/wav")})
            else:
                answer = services.post_chat(self._http, self.name, self._chat(style, model, sound, lang),
                                            self._plain)
        except Exception as error:
            raise SttError(f"{title} can't be reached: {error}") from error
        if answer.status_code >= 400:
            if answer.status_code == 429:
                self._wait_until = self._clock() + services.retry_after(answer)
            raise SttError(services.failure(self.name, answer))
        try:
            body = answer.json()
            return self._read_whisper(body, lang) if style == "whisper" else self._read_chat(style, body, lang)
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as error:
            raise SttError(f"{title}'s answer could not be read") from error

    def _detailed(self, model: str) -> bool:
        """Only Whisper models give the language and certainty ("verbose_json")."""
        return "whisper" in model.lower()

    @staticmethod
    def _chat(style: str, model: str, sound: bytes, lang: str | None) -> dict:
        encoded = base64.b64encode(sound).decode()
        if style == "qwen":
            options = {"enable_itn": False}
            if lang:
                options["language"] = lang
            return {"model": model, "asr_options": options, "messages": [{"role": "user", "content": [
                {"type": "input_audio", "input_audio": {"data": f"data:audio/wav;base64,{encoded}"}}]}]}
        return {"model": model, "temperature": 0, "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": HEAR_PROMPT}, {"role": "user", "content": [
                    {"type": "text", "text": f"Spoken language: {lang or 'not known, find it'}"},
                    {"type": "input_audio", "input_audio": {"data": encoded, "format": "wav"}}]}]}

    @staticmethod
    def _read_whisper(body: dict, lang: str | None) -> tuple[Heard, float | None]:
        text = (body.get("text") or "").strip()
        code = lang or language_code(str(body.get("language") or ""), text)
        # avg_logprob: the average log-probability of the word pieces in a segment
        logprobs = [float(s["avg_logprob"]) for s in body.get("segments") or []
                    if isinstance(s, dict) and s.get("avg_logprob") is not None]
        certainty = math.exp(sum(logprobs) / len(logprobs)) if logprobs else None
        return tidy(text, code), certainty

    @staticmethod
    def _read_chat(style: str, body: dict, lang: str | None) -> tuple[Heard, float | None]:
        message = body["choices"][0]["message"]
        content = message.get("content") or ""
        if isinstance(content, list):          # some services answer in parts
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        if style == "qwen":
            text, found = content.strip(), ""
            for note in message.get("annotations") or []:
                if isinstance(note, dict) and note.get("language"):
                    found = str(note["language"])
        else:
            content = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
            answer = json.loads(content or "{}")
            text, found = str(answer.get("text") or "").strip(), str(answer.get("language") or "")
        return tidy(text, lang or language_code(found, text)), None
