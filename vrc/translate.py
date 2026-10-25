"""What every translator shares: the language names, the prompt, and the error they raise.

The translators themselves are in engine/translators.py (the service picked in Settings).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import re
import time

TARGET_NAMES = {"en": "English", "zh": "Simplified Chinese", "vi": "Vietnamese",
                "ja": "Japanese", "ko": "Korean",
                "yue": "Hong Kong Cantonese (written the way Hong Kong people chat, in Traditional "
                       "Chinese characters)"}


class TranslateError(Exception):
    """No translation right now; the message says why in plain words."""


def can_reuse_original(text, source, target):
    # shortcut: detect CJK words in Latin output; other mixed-language pairs need evidence before expanding this check.
    foreign = target in ("en", "vi") and re.search(
        r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uff66-\uff9d\u1100-\u11ff\u3130-\u318f\uac00-\ud7af]", text)
    return source == target and not foreign


def translate_targets(translator, text, targets, source="", heard=False, on_result=None):
    """Translate each distinct destination once; one failed language does not hide the others."""
    translations, errors = {}, {}
    targets = list(dict.fromkeys(code for code in targets if code))
    def ready(target, value, error=None):
        translations[target] = value
        if error is not None:
            errors[target] = error
        if on_result is not None and value and len(translations) < len(targets):
            on_result(translations.copy())

    # Original text is already available, even if it is listed after a slow target.
    if source in targets and can_reuse_original(text, source, source):
        ready(source, text)
    pending = [target for target in targets if target not in translations]

    def run(target):
        started = time.perf_counter()
        try:
            return ((translator.translate(text, target, source, heard=True) if heard
                     else translator.translate(text, target, source)), None)
        except Exception as error:
            return "", error
        finally:
            logging.getLogger("engine.translation").info("translation target=%s duration_ms=%d", target,
                                                       (time.perf_counter() - started) * 1000)

    # Only online adapters opt in. Local inference retains its shared model/CPU budget.
    if len(pending) > 1 and getattr(translator, "parallel_targets", False):
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="translate-target") as pool:
            jobs = {pool.submit(run, target): target for target in pending}
            for job in as_completed(jobs):
                ready(jobs[job], *job.result())
    else:
        for target in pending:
            ready(target, *run(target))
    return ({target: translations[target] for target in targets},
            {target: errors[target] for target in targets if target in errors})


def chat_messages(text: str, target: str, likely_source: str = "", heard: bool = False) -> list[dict]:
    """`heard`: the text came from speech recognition, not from typing."""
    name = TARGET_NAMES[target]
    system = ("You translate chat messages for a player talking with other people in VRChat "
              f"(casual spoken conversation). Translate the user's message into {name}. Reply with "
              "the translation only: no explanations, notes, quotes or romanization. Keep it "
              "natural and conversational, about as short as the original. Keep names, numbers "
              f"and emoji as they are. If the message is already in {name}, reply with it unchanged.")
    if likely_source in TARGET_NAMES and likely_source != target:
        system += f" The message is most likely in {TARGET_NAMES[likely_source]}."
    if heard:
        # in the benchmark this wording helped recover misheard names
        system += (" The text was written down by speech recognition, so a word may be misheard: "
                   "translate what the speaker most likely meant.")
    return [{"role": "system", "content": system}, {"role": "user", "content": text}]


class NoTranslator:
    """Stands in when the speech engine (and its translators) is not installed: typed text
    then goes to the chatbox as it was typed, with the reason shown on its line."""

    def prepare(self) -> None:
        pass

    def translate(self, text: str, target: str, likely_source: str = "", heard: bool = False) -> str:
        raise TranslateError("no translator is installed")
