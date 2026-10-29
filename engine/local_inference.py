"""Local hearing and translation with a conservative CPU/GPU budget for gaming."""
from __future__ import annotations

from collections import Counter
import logging
import re
import threading
import time

from . import gpu_budget, local_model, runtime, stt
from .stt import Heard, LocalWhisper, SttError, guess_language, in_own_script, mostly_chinese, tidy
from .whisper_vulkan import VulkanWhisper
from vrc.translate import TARGET_NAMES, TranslateError, can_reuse_original


class LocalHearing:
    name = "local"

    def __init__(self):
        self._selected = ""
        self._engine = None

    def _current(self):
        selected = local_model.selected()
        if selected != self._selected:
            self.close()          # Release the previous model before allocating the next one.
            if selected == "whisper-turbo-vulkan":
                self._engine = VulkanWhisper()
            else:
                self._engine = LocalSenseVoice() if selected == "sensevoice" else LocalWhisper(selected)
            self._selected = selected
        return self._engine

    def close(self):
        """Drop the current recognizer and its weights. The next use loads it again.
        True when something resident was freed."""
        engine, self._engine = self._engine, None
        self._selected = ""
        if engine is not None and hasattr(engine, "close"):
            engine.close()
        return engine is not None

    def load(self):
        self._current().load()

    def transcribe(self, samples, lang, prefer=()) -> Heard:
        return self._current().transcribe(samples, lang, prefer=prefer)


class LocalSenseVoice:
    def __init__(self):
        self._recognizer = None

    def close(self):
        """Free the ONNX session (and its CPU threads) without touching the downloaded files."""
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
                language="auto", use_itn=True, num_threads=runtime.cpu_threads(), provider="cpu")
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


def _drop_weights(engine) -> bool:
    """Free one local translator's weights (and llama.cpp's context) under the shared lock."""
    model, tokenizer = engine._model, engine._tokenizer
    if model is None and tokenizer is None:
        return False
    engine._model = engine._tokenizer = None
    engine._device = "cpu"
    close = getattr(model, "close", None)
    if not callable(close):
        close = getattr(model, "unload_model", None)
    if callable(close):
        try:
            close()
        except Exception as error:      # weights are dropped even if the native close fails
            logging.getLogger(__name__).warning("local translation close failed: %s", error)
    del model, tokenizer
    return True


def _release_other_translator(current):
    # All runtimes share the lock: switching releases weights without interrupting a call.
    for engine in (translator, qwen_translator, hy_mt_translator):
        if engine is not current:
            _drop_weights(engine)
            engine._gpu_disabled_reason = ""  # a different model is now selected


def release_local_translation(should_release=None) -> bool:
    """Free every resident local translation model. Called when an online provider is selected,
    so its weights, KV cache and worker threads stop using memory and CPU immediately."""
    with _translation_lock:
        if should_release is not None and not should_release():
            return False
        released = False
        for engine in (translator, qwen_translator, hy_mt_translator):
            released = _drop_weights(engine) or released
    if released:
        logging.getLogger(__name__).info("released local translation weights")
    return released


def check_local_gpu_budget() -> None:
    """Check idle GPU weights from the existing worker without delaying active translation."""
    if not _translation_lock.acquire(blocking=False):
        return
    try:
        for engine in (translator, qwen_translator):
            engine._check_gpu_budget()
    finally:
        _translation_lock.release()


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
        self._device = "cpu"
        self._gpu_disabled_reason = ""
        self._gpu_checked_at = 0.0

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
        self._load_ct2("Translator")

    def _disable_gpu(self, reason):
        _drop_weights(self)
        self._gpu_disabled_reason = reason
        logging.getLogger(__name__).warning("local translation model=%s switching to CPU: %s", self.model_id, reason)

    def _check_gpu_budget(self, *, force=False):
        if self._device != "cuda":
            return
        now = time.monotonic()
        if not force and now - self._gpu_checked_at < gpu_budget.PROBE_INTERVAL_S:
            return
        self._gpu_checked_at = now
        free = gpu_budget.free_vram_mib()
        if free is None or free < gpu_budget.RESERVE_MIB:
            self._disable_gpu("free GPU memory is unavailable" if free is None else
                              f"only {free} MiB free; preserving game memory")

    def _gpu_failed(self, error):
        if self._device == "cuda" and any(part in str(error).lower() for part in (
                "out of memory", "out_of_memory", "cuda", "cublas", "cudnn")):
            # Do not retry a failing GPU on every line. The next request loads CPU weights.
            self._disable_gpu(f"GPU inference failed: {error}")

    def _load_ct2(self, kind):
        self._check_gpu_budget()
        if self._model is None:
            _release_other_translator(self)
            import ctranslate2
            from tokenizers import Tokenizer
            root = local_model.model_folder(self.model_id)
            tokenizer = Tokenizer.from_file(str(root / "tokenizer.json"))
            device, reason = (("cpu", self._gpu_disabled_reason) if self._gpu_disabled_reason else
                              gpu_budget.select_device(ctranslate2, self.model_id))
            create = getattr(ctranslate2, kind)
            options = dict(inter_threads=1, intra_threads=runtime.cpu_threads())
            if device == "cuda":
                try:
                    stt._add_gpu_libraries()
                    model = create(str(root), device="cuda", compute_type="int8_float16", **options)
                except Exception as error:
                    device = "cpu"
                    reason = self._gpu_disabled_reason = f"GPU loading failed: {error}"
                    logging.getLogger(__name__).warning("local translation model=%s %s", self.model_id, reason)
            if device == "cpu":
                model = create(str(root), device="cpu", compute_type="int8", **options)
            self._model, self._tokenizer = model, tokenizer
            self._device = device
            self._gpu_checked_at = time.monotonic()
            if device == "cuda":
                self._check_gpu_budget(force=True)
                if self._model is None:
                    self._load_ct2(kind)  # The failed reserve check pins this model to CPU.
                    return
            logging.getLogger(__name__).info("local translation model=%s device=%s threads=%s reason=%s",
                                             self.model_id, device, options["intra_threads"], reason)

    def translate(self, text, target, likely_source="", heard=False):
        source = likely_source or guess_language(text)
        if source not in LANGUAGES or target not in LANGUAGES:
            raise TranslateError("Local NLLB does not support this language in the app")
        if can_reuse_original(text, source, target) or not re.search(r"\w", text):
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
                self._gpu_failed(error)
                err = TranslateError(f"Local NLLB could not translate: {error}")
                err.wait = 0
                raise err from error


def qwen_messages(text: str, target: str, likely_source: str = "") -> list[dict]:
    name = TARGET_NAMES[target]
    system = (f"You translate chat messages into {name}. "
              "Reply with the translation only: no explanations, no notes, no quotes, no romanization, and no reasoning.")
    if likely_source in TARGET_NAMES and likely_source != target:
        system += f" The message is most likely in {TARGET_NAMES[likely_source]}."
    return [{"role": "system", "content": system}, {"role": "user", "content": text}]


class LocalQwenTranslator(LocalTranslator):
    model_id = "qwen3-1.7b-ct2"

    def _load(self):
        self._load_ct2("Generator")

    def translate(self, text, target, likely_source="", heard=False):
        source = likely_source or guess_language(text)
        if source not in LANGUAGES or target not in LANGUAGES:
            raise TranslateError("Local Qwen does not support this language in the app")
        if can_reuse_original(text, source, target) or not re.search(r"\w", text):
            return text
        problem = local_model.missing("qwen3-1.7b-ct2")
        if problem:
            error = TranslateError(problem)
            error.wait = 0
            raise error
        with self._lock:
            try:
                self._load()
                messages = qwen_messages(text, target, source)
                prompt = "".join(f"<|im_start|>{message['role']}\n{message['content']}<|im_end|>\n" for message in messages)
                # Pinned Qwen3 chat template's enable_thinking=False generation prefix.
                prompt += "<|im_start|>assistant\n<think>\n\n</think>\n\n"
                tokens = self._tokenizer.encode(prompt, add_special_tokens=False).tokens
                if len(tokens) > 1024:
                    raise ValueError("message too long for local Qwen; split it into shorter messages")
                # CTranslate2 keeps the computed state of a static prompt between lines; it must be
                # an exact token prefix, so anything else is sent whole as before.
                fixed = self._tokenizer.encode("<|im_start|>system\n" + qwen_messages("", target)[0]["content"],
                                               add_special_tokens=False).tokens
                static = fixed if tokens[:len(fixed)] == fixed else None
                result = self._model.generate_batch(
                    [tokens[len(fixed):] if static else tokens], static_prompt=static,
                    beam_size=1, sampling_topk=1, max_length=512,
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
                if not answer or "<think>" in answer or "</think>" in answer or re.match(
                        r"(?i)^(?:okay,?\s+)?(?:let's see|the user\b|i need to\b)", answer):
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
                self._gpu_failed(error)
                err = TranslateError(f"Local Qwen could not translate: {error}")
                err.wait = 0
                raise err from error


HY_MT_NAMES = {"en": ("English", "英语"), "zh": ("Chinese", "中文"), "yue": ("Cantonese", "粤语"),
               "vi": ("Vietnamese", "越南语"), "ja": ("Japanese", "日语"), "ko": ("Korean", "韩语")}


def hy_mt_prompt(text: str, target: str, source: str) -> str:
    """Tencent's default translation prompt; its Chinese wording when Chinese is involved."""
    english, chinese = HY_MT_NAMES[target]
    if {source, target} & {"zh", "yue"}:
        return f"将以下文本翻译为{chinese}，注意只需要输出翻译后的结果，不要额外解释：\n\n{text}"
    return (f"Translate the following text into {english}. Note that you should only output the "
            f"translated result without any additional explanation:\n\n{text}")


class LocalHyMTTranslator(LocalTranslator):
    model_id = "hy-mt2-1.8b"

    def _load(self):
        if self._model is None:
            _release_other_translator(self)
            from llama_cpp import Llama
            path = local_model.model_folder(self.model_id) / "model.gguf"
            threads = runtime.cpu_threads()
            self._model = Llama(str(path), n_ctx=2048, n_threads=threads, n_threads_batch=threads, n_gpu_layers=0,
                                verbose=False)

    def _tokens(self, text):
        return self._model.tokenize(text.encode("utf-8"), add_bos=False)

    def translate(self, text, target, likely_source="", heard=False):
        source = likely_source or guess_language(text)
        if source not in LANGUAGES or target not in LANGUAGES:
            raise TranslateError("Local Hy-MT2 does not support this language in the app")
        if can_reuse_original(text, source, target) or not re.search(r"\w", text):
            return text
        problem = local_model.missing(self.model_id)
        if problem:
            error = TranslateError(problem)
            error.wait = 0
            raise error
        with self._lock:
            try:
                self._load()
                prompt = hy_mt_prompt(text, target, source)
                if len(self._tokens(prompt)) > 1024:
                    raise ValueError("message too long for local Hy-MT2; split it into shorter messages")
                # Greedy, so a repeated line gets the same answer (engine.translators.Remembered).
                result = self._model.create_chat_completion(
                    [{"role": "user", "content": prompt}], temperature=0.0, top_k=1, top_p=1.0,
                    max_tokens=512, repeat_penalty=1.05)["choices"][0]
                answer = (result["message"]["content"] or "").strip()
                if result.get("finish_reason") != "stop":
                    raise ValueError("translation did not finish; try a shorter message")
                if not answer:
                    raise ValueError("the model did not return a translation")
                if translation_loop(self._tokens(answer), self._tokens(text)):
                    raise ValueError("the translation kept repeating")
                if target in ("en", "vi") and mostly_chinese(answer):
                    raise ValueError("the model answered in Chinese instead of translating")
                if not in_own_script(answer, target):
                    raise ValueError("the model did not use the requested language")
                if target in ("zh", "yue"):
                    import zhconv
                    answer = zhconv.convert(answer, "zh-cn" if target == "zh" else "zh-hk")
                return " ".join(answer.split())
            except Exception as error:
                err = TranslateError(f"Local Hy-MT2 could not translate: {error}")
                err.wait = 0
                raise err from error


translator = LocalTranslator()  # Share weights between typed text and both speech queues.
qwen_translator = LocalQwenTranslator()
hy_mt_translator = LocalHyMTTranslator()
