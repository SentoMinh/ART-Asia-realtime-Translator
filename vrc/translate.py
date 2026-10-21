"""What every translator shares: the language names, the prompt, and the error they raise.

The translators themselves are in engine/translators.py (the online service picked in
Settings → Models, plus any add-on found on this PC).
"""
from __future__ import annotations

TARGET_NAMES = {"en": "English", "zh": "Simplified Chinese", "vi": "Vietnamese",
                "ja": "Japanese", "ko": "Korean",
                "yue": "Hong Kong Cantonese (written the way Hong Kong people chat, in Traditional "
                       "Chinese characters)"}


class TranslateError(Exception):
    """No translation right now; the message says why in plain words."""


def translate_targets(translator, text, targets, source="", heard=False):
    """Translate each distinct destination once; one failed language does not hide the others."""
    translations, errors = {}, {}
    for target in dict.fromkeys(code for code in targets if code):
        if target == source:
            translations[target] = text
            continue
        try:
            translations[target] = (translator.translate(text, target, source, heard=True) if heard
                                    else translator.translate(text, target, source))
        except Exception as error:
            translations[target] = ""
            errors[target] = error
    return translations, errors


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
