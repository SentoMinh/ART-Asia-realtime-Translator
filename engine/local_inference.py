"""Local hearing choices and CPU translation; model files stay in the user's cache."""
from __future__ import annotations

import threading

from . import local_model
from .stt import Heard, LocalWhisper, SttError, guess_language, tidy
from vrc.translate import TranslateError


class LocalHearing:
    name = "local"

    def __init__(self):
        self._selected = ""
        self._engine = None

    def _current(self):
        selected = local_model.selected()
        if selected != self._selected:
            self._engine = None  # Release the previous model before allocating the next one.
            self._engine = LocalSenseVoice() if selected == "sensevoice" else LocalWhisper(selected)
            self._selected = selected
        return self._engine

    def load(self):
        self._current().load()

    def transcribe(self, samples, lang, prefer=()) -> Heard:
        return self._current().transcribe(samples, lang, prefer=prefer)


class LocalSenseVoice:
    def __init__(self):
        self._recognizer = None

    def load(self):
        if self._recognizer is not None:
            return
        problem = local_model.missing("sensevoice")
        if problem:
            raise SttError(problem)
        try:
            import sherpa_onnx
            root = local_model.model_folder("sensevoice")
            self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=str(root / "model.int8.onnx"), tokens=str(root / "tokens.txt"),
                language="auto", use_itn=True, num_threads=2, provider="cpu")
        except Exception as error:
            raise SttError(f"SenseVoice could not be loaded: {error}") from error

    def transcribe(self, samples, lang, prefer=()) -> Heard:
        if lang and lang not in ("en", "zh", "yue", "ja", "ko"):
            raise SttError("SenseVoice supports Chinese, Cantonese, English, Japanese and Korean; choose Whisper for this language")
        self.load()
        try:
            stream = self._recognizer.create_stream()
            stream.accept_waveform(16000, samples)
            self._recognizer.decode_stream(stream)
            result = stream.result
            code = str(result.lang or "").strip("<|>") or lang or guess_language(result.text)
            return tidy(result.text.strip(), code)
        except Exception as error:
            raise SttError(f"SenseVoice could not transcribe: {error}") from error


LANGUAGES = {"en": "eng_Latn", "vi": "vie_Latn", "zh": "zho_Hans", "yue": "yue_Hant",
             "ja": "jpn_Jpan", "ko": "kor_Hang"}


class LocalTranslator:
    def __init__(self):
        self._model = self._tokenizer = None
        self._lock = threading.Lock()

    def prepare(self):
        pass  # Load on the translation worker, never on the UI thread.

    def translate(self, text, target, likely_source="", heard=False):
        source = likely_source or guess_language(text)
        if source not in LANGUAGES or target not in LANGUAGES:
            raise TranslateError("Local NLLB does not support this language in the app")
        if source == target:
            return text
        problem = local_model.missing("nllb-200-ct2")
        if problem:
            error = TranslateError(problem)
            error.wait = 0
            raise error
        with self._lock:
            try:
                if self._model is None:
                    import ctranslate2
                    from tokenizers import Tokenizer
                    root = local_model.model_folder("nllb-200-ct2")
                    tokenizer = Tokenizer.from_file(str(root / "tokenizer.json"))
                    model = ctranslate2.Translator(str(root), device="cpu", compute_type="int8",
                                                  inter_threads=1, intra_threads=2)
                    self._model, self._tokenizer = model, tokenizer
                # NLLB's source format is language token + text + EOS.
                tokens = [LANGUAGES[source], *self._tokenizer.encode(text, add_special_tokens=False).tokens, "</s>"]
                result = self._model.translate_batch([tokens], target_prefix=[[LANGUAGES[target]]], beam_size=1)
                translated = result[0].hypotheses[0][1:]
                ids = [self._tokenizer.token_to_id(token) for token in translated]
                answer = self._tokenizer.decode(ids, skip_special_tokens=True).strip()
                if not answer:
                    raise ValueError("the translation came back empty")
                return answer
            except Exception as error:
                raise TranslateError(f"Local NLLB could not translate: {error}") from error


translator = LocalTranslator()  # Share one model between typed text and both speech queues.
