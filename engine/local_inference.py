"""Local hearing choices and CPU translation; model files stay in the user's cache."""
from __future__ import annotations

from collections import Counter
import logging
import re
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


def translation_sentences(text):
    """Keep punctuation while giving the sentence-trained model each sentence."""
    sentences, start = [], 0
    for boundary in re.finditer(r'''([.!?。！？]+)["'”’」』）)]*(\s*)''', text):
        punctuation = boundary[1]
        if not any(char in "。！？" for char in punctuation) and not boundary[2] and boundary.end() < len(text):
            continue  # Decimal points, URLs and abbreviations inside a word.
        if punctuation == "." and re.search(
                r"(?:\b(?i:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|vs|etc|e\.g|i\.e)|\b[A-Z]|\b(?:[A-Za-z]\.)+[A-Za-z])\.$",
                text[:boundary.start() + 1]):
            continue
        if punctuation == "...":
            continue
        sentences.append(text[start:boundary.end()].strip())
        start = boundary.end()
    if text[start:].strip():
        sentences.append(text[start:].strip())
    # shortcut: conservative punctuation rules, use a language-aware splitter if ambiguous boundaries recur.
    return sentences


def translation_loop(tokens, source_tokens):
    if len(tokens) < max(48, 2 * len(source_tokens)):
        return False
    ngrams = Counter(tuple(tokens[index:index + 4]) for index in range(len(tokens) - 3))
    return max(ngrams.values(), default=0) >= 6


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
                tokens = [[LANGUAGES[source], *self._tokenizer.encode(sentence, add_special_tokens=False).tokens, "</s>"]
                          for sentence in translation_sentences(text)]
                if not tokens:
                    raise ValueError("the translation came back empty")
                results = self._model.translate_batch(tokens, target_prefix=[[LANGUAGES[target]]] * len(tokens), beam_size=1)
                if len(results) != len(tokens):
                    raise ValueError("the translation omitted a sentence")
                answers = []
                for original, result in zip(tokens, results):
                    translated = result.hypotheses[0][1:]
                    if translation_loop(translated, original):
                        logging.getLogger(__name__).warning("Local NLLB repetition detected (%s -> %s); retrying sentence once", source, target)
                        retry = self._model.translate_batch([original], target_prefix=[[LANGUAGES[target]]],
                                                            beam_size=1, no_repeat_ngram_size=4)
                        translated = retry[0].hypotheses[0][1:]
                        if translation_loop(translated, original):
                            raise ValueError("the translation kept repeating")
                    ids = [self._tokenizer.token_to_id(token) for token in translated]
                    answer = self._tokenizer.decode(ids, skip_special_tokens=True).strip()
                    if not answer:
                        raise ValueError("a sentence translation came back empty")
                    answers.append(answer)
                return " ".join(answers)
            except Exception as error:
                raise TranslateError(f"Local NLLB could not translate: {error}") from error


translator = LocalTranslator()  # Share one model between typed text and both speech queues.
