"""Local hearing choices and CPU translation; model files stay in the user's cache."""
from __future__ import annotations

from collections import Counter
import logging
import re
import threading
import time

from . import local_model
from .stt import Heard, LocalWhisper, SttError, guess_language, in_own_script, mostly_chinese, tidy
from .whisper_vulkan import VulkanWhisper
from vrc.translate import TranslateError, can_reuse_original, chat_messages


class LocalHearing:
    name = "local"

    def __init__(self):
        self._selected = ""
        self._engine = None

    def _current(self):
        selected = local_model.selected()
        if selected != self._selected:
            self.close()
            self._engine = None  # Release the previous model before allocating the next one.
            if selected == "whisper-turbo-vulkan":
                self._engine = VulkanWhisper()
            else:
                self._engine = LocalSenseVoice() if selected == "sensevoice" else LocalWhisper(selected)
            self._selected = selected
        return self._engine

    def close(self):
        if self._engine is not None and hasattr(self._engine, "close"):
            self._engine.close()

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
_translation_lock = threading.Lock()


def _release_other_translator(current):
    # Both runtimes share the lock: switching releases weights without interrupting a call.
    for engine in (translator, qwen_translator):
        if engine is not current:
            engine._model = engine._tokenizer = None


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
    model_id = "nllb-200-ct2"

    def __init__(self):
        self._model = self._tokenizer = None
        self._lock = _translation_lock

    def prepare(self):
        # The backend invokes this on its worker before the first typed request.
        try:
            with self._lock:
                if self._model is not None or local_model.missing(self.model_id):
                    return
                started = time.perf_counter()
                self._load()
            logging.getLogger(__name__).info("local translation model=%s preparation_ms=%d", self.model_id,
                                             (time.perf_counter() - started) * 1000)
        except Exception as error:
            logging.getLogger(__name__).warning("local translation preparation deferred: %s", error)

    def _load(self):
        if self._model is None:
            _release_other_translator(self)
            import ctranslate2
            from tokenizers import Tokenizer
            root = local_model.model_folder(self.model_id)
            tokenizer = Tokenizer.from_file(str(root / "tokenizer.json"))
            model = ctranslate2.Translator(str(root), device="cpu", compute_type="int8",
                                          inter_threads=1, intra_threads=2)
            self._model, self._tokenizer = model, tokenizer

    def translate(self, text, target, likely_source="", heard=False):
        source = likely_source or guess_language(text)
        if source not in LANGUAGES or target not in LANGUAGES:
            raise TranslateError("Local NLLB does not support this language in the app")
        if can_reuse_original(text, source, target):
            return text
        problem = local_model.missing("nllb-200-ct2")
        if problem:
            error = TranslateError(problem)
            error.wait = 0
            raise error
        with self._lock:
            try:
                self._load()
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


class LocalQwenTranslator(LocalTranslator):
    model_id = "qwen3-1.7b-ct2"

    def _load(self):
        if self._model is None:
            _release_other_translator(self)
            import ctranslate2
            from tokenizers import Tokenizer
            root = local_model.model_folder(self.model_id)
            tokenizer = Tokenizer.from_file(str(root / "tokenizer.json"))
            model = ctranslate2.Generator(str(root), device="cpu", compute_type="int8",
                                         inter_threads=1, intra_threads=2)
            self._model, self._tokenizer = model, tokenizer

    def translate(self, text, target, likely_source="", heard=False):
        source = likely_source or guess_language(text)
        if source not in LANGUAGES or target not in LANGUAGES:
            raise TranslateError("Local Qwen does not support this language in the app")
        if can_reuse_original(text, source, target):
            return text
        problem = local_model.missing("qwen3-1.7b-ct2")
        if problem:
            error = TranslateError(problem)
            error.wait = 0
            raise error
        with self._lock:
            try:
                self._load()
                messages = chat_messages(text, target, source, heard=heard)
                prompt = "".join(f"<|im_start|>{message['role']}\n{message['content']}<|im_end|>\n" for message in messages)
                # Pinned Qwen3 chat template's enable_thinking=False generation prefix.
                prompt += "<|im_start|>assistant\n<think>\n\n</think>\n\n"
                tokens = self._tokenizer.encode(prompt, add_special_tokens=False).tokens
                if len(tokens) > 1024:
                    raise ValueError("message too long for local Qwen; split it into shorter messages")
                result = self._model.generate_batch(
                    [tokens], beam_size=1, sampling_topk=1, max_length=512,
                    end_token=["<|im_end|>", "<|endoftext|>"], return_end_token=True,
                    include_prompt_in_result=False)[0]
                output = result.sequences[0]
                if not output or output[-1] not in ("<|im_end|>", "<|endoftext|>"):
                    raise ValueError("translation did not finish; try a shorter message")
                output = output[:-1]
                original = self._tokenizer.encode(text, add_special_tokens=False).tokens
                if translation_loop(output, original):
                    raise ValueError("the translation kept repeating")
                ids = [self._tokenizer.token_to_id(token) for token in output]
                answer = self._tokenizer.decode(ids, skip_special_tokens=True).strip()
                if not answer or "<think>" in answer or "</think>" in answer:
                    raise ValueError("the model did not return a translation")
                if target in ("en", "vi") and mostly_chinese(answer):
                    raise ValueError("the model answered in Chinese instead of translating")
                if not in_own_script(answer, target):
                    raise ValueError("the model did not use the requested language")
                if target in ("zh", "yue"):
                    import zhconv
                    answer = zhconv.convert(answer, "zh-cn" if target == "zh" else "zh-hk")
                return " ".join(answer.split())
            except Exception as error:
                raise TranslateError(f"Local Qwen could not translate: {error}") from error


translator = LocalTranslator()  # Share weights between typed text and both speech queues.
qwen_translator = LocalQwenTranslator()
