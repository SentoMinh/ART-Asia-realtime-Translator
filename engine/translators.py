"""Text translators with fallback.

Live voice chat needs many translations a day, and a model can reach its limit, so several
can be chained: when one says "limit reached" or can't be reached, it is skipped for a while
and the next one answers. Settings → Models picks the service; several models of one service
can be listed with commas (engine/services.py).

Every translator has prepare() and translate(text, target, likely_source, heard=False) -> str,
and raises vrc.translate.TranslateError with a plain-words reason.

Only explicitly configured models of the selected service are tried.
"""
from __future__ import annotations

import time
import threading

from vrc.translate import TranslateError, chat_messages

from . import services
from .stt import guess_language, mostly_chinese

COOL_OFF_S = 60           # a translator that failed is skipped this long...
LIMIT_COOL_OFF_S = 600    # ...and this long when it said its limit is reached


class ServiceTranslator:
    """One chat model of an online service (engine/services.py). The address and key are read
    again for every line, so a change in Settings works at once."""

    def __init__(self, service: str, model: str, http=None):
        self.service = service
        self.model = model
        self._http = http
        self._http_lock = threading.Lock()
        self._plain: set[str] = set()

    def prepare(self) -> None:
        pass

    def translate(self, text: str, target: str, likely_source: str = "", heard: bool = False) -> str:
        problem = services.missing(self.service)
        if problem:
            error = TranslateError(problem)
            error.wait = 0            # ask again at once: the key may be there next time
            raise error
        name = services.title(self.service)
        with self._http_lock:
            if self._http is None:
                import httpx
                timeout = 60 if services.is_custom(self.service) else 15
                self._http = httpx.Client(timeout=timeout)
        body = {"model": self.model, "temperature": 0, "max_tokens": 1024,
                "messages": chat_messages(text, target, likely_source, heard=heard)}
        direct = services.is_custom(self.service) and self.model == "nllb-200-ct2"
        try:
            if direct:
                # This translation-only server accepts language codes, not chat prompts.
                answer = self._http.post(services.setting(self.service, "url").rstrip("/") + "/translate",
                                         json={"text": text, "source_language": likely_source or guess_language(text),
                                               "target_language": target}, headers=services.auth(self.service))
            else:
                answer = services.post_chat(self._http, self.service, body, self._plain)
        except Exception as error:
            raise TranslateError(f"{name} can't be reached: {error}") from error
        if answer.status_code >= 400:
            error = TranslateError(services.failure(self.service, answer))
            if answer.status_code == 429:
                error.wait = services.retry_after(answer)     # how long to leave it alone
            raise error
        try:
            response = answer.json()
            text_out = (response["translated_text"] if direct else response["choices"][0]["message"].get("content")) or ""
            if not isinstance(text_out, str):
                raise ValueError("translation is not text")
        except (ValueError, KeyError, IndexError, AttributeError) as error:
            raise TranslateError(f"{name}'s answer could not be read") from error
        if not text_out.strip():
            raise TranslateError("the translation came back empty")
        if target in ("en", "vi") and mostly_chinese(text_out):
            # Asked about misheard speech, a model sometimes corrects the Chinese instead of
            # translating it: let the next model answer this line, without resting this one
            error = TranslateError(f"{self.model} answered in Chinese instead of translating")
            error.wait = 0
            raise error
        return " ".join(text_out.split())


class Chain:
    """Tries the translators in order; one that fails is skipped for a while."""

    def __init__(self, translators: list[tuple[str, object]], clock=time.monotonic, on_switch=None):
        self._translators = translators          # (name, translator), best first
        self._clock = clock
        self._skip_until: dict[str, float] = {}
        self._errors: dict[str, str] = {}
        self._state_lock = threading.Lock()
        self.last_used = ""                      # name of the one that answered last
        self.on_switch = on_switch

    def prepare(self) -> None:
        if self._translators:
            self._translators[0][1].prepare()

    def translate(self, text: str, target: str, likely_source: str = "", heard: bool = False) -> str:
        """`heard`: the text comes from speech recognition, so a word may be misheard."""
        problem: TranslateError | None = None
        for name, translator in self._translators:
            with self._state_lock:
                if self._clock() < self._skip_until.get(name, 0.0):
                    if name in self._errors:
                        problem = TranslateError(self._errors[name])
                    continue
            try:
                answer = translator.translate(text, target, likely_source, heard=heard)
            except TranslateError as error:
                problem = error
                wait = getattr(error, "wait", None)      # the translator said how long
                if wait is None:
                    limit = "limit" in str(error) or "used up" in str(error)
                    wait = LIMIT_COOL_OFF_S if limit else COOL_OFF_S
                with self._state_lock:
                    until = self._clock() + wait
                    if until >= self._skip_until.get(name, 0.0):
                        self._errors[name] = str(error)
                        self._skip_until[name] = until
                continue
            with self._state_lock:
                # Another in-flight language may have hit a limit. Keep its cooldown/error.
                if self._clock() >= self._skip_until.get(name, 0.0):
                    self._errors.pop(name, None)
                prev_used = self.last_used
                self.last_used = name
            if self.on_switch and (prev_used != name or not prev_used):
                self.on_switch(name)
            return answer
        raise problem or TranslateError("every translator is resting after an error; try again soon")


class ServiceChain:
    """Only the models explicitly configured for the selected service.
    `pick()` says which service that is right now; it can change while the program runs."""

    def __init__(self, pick=lambda: "", clock=time.monotonic, on_switch=None):
        self._pick = pick
        self._clock = clock
        self._chains: dict[tuple, Chain] = {}     # one per provider configuration, keeping its rests
        self._chain_lock = threading.Lock()
        self.last_used = ""
        self.on_switch = on_switch

    def _chain(self) -> Chain:
        with self._chain_lock:
            return self._configured_chain()

    @property
    def parallel_targets(self) -> bool:
        return (self._pick() or services.default_service()) != "local"

    def _configured_chain(self) -> Chain:
        service = self._pick() or services.default_service()
        models = tuple(services.translate_models(service))
        key = (service, models, services.setting(service, "url"), services.setting(service, "key"))
        if key not in self._chains:
            if service == "local":
                from .local_inference import translator, qwen_translator
                model = models[0]
                choices = [(f"local:{model}", qwen_translator if model == "qwen3-1.7b-ct2" else translator)]
            else:
                choices = [(f"{service}:{model}", ServiceTranslator(service, model)) for model in models]
            self._chains[key] = Chain(
                choices,
                self._clock,
                on_switch=self._on_model_switch)
        return self._chains[key]

    def _on_model_switch(self, name: str) -> None:
        self.last_used = name
        if self.on_switch:
            self.on_switch(name)

    def names(self) -> list[str]:
        return [name for name, _ in self._chain()._translators]

    def prepare(self) -> None:
        self._chain().prepare()

    def translate(self, text: str, target: str, likely_source: str = "", heard: bool = False) -> str:
        chain = self._chain()
        service = self._pick() or services.default_service()
        models = tuple(services.translate_models(service))
        if not chain._translators:
            service = self._pick() or services.default_service()
            raise TranslateError(f"{services.title(service)} has no translating model yet (Settings → Models)")
        answer = chain.translate(text, target, likely_source, heard=heard)
        self.last_used = chain.last_used
        self.last_result = (time.monotonic(), service, models, self.last_used)
        if self.on_switch and self.last_used:
            self.on_switch(self.last_used)
        return answer
