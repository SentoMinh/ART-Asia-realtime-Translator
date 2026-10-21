"""The contract between the window and the translator engine.

The window only talks to a Backend: it listens to the signals and calls the
methods. The real engine subclasses Backend; DemoBackend (demo_backend.py)
plays example lines so the window can be used before the engine exists.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

LANGS = {"en": "English", "zh": "Chinese", "yue": "Cantonese", "vi": "Vietnamese",
         "ja": "Japanese", "ko": "Korean"}   # zh = Mandarin
# What the pickers offer. Picking a language makes the engine focus on it (Cantonese can't be
# told from Mandarin by sound alone, so it needs its own entry).
PICK_LANGS = tuple(LANGS)
# Languages the app does not translate: a line in one of them is only announced in the chat
# log ("【Speaking Spanish】"). Codes as the speech model reports them; others show as the code.
OTHER_LANGS = {"es": "Spanish", "fr": "French", "de": "German",
               "ru": "Russian", "th": "Thai", "id": "Indonesian", "pt": "Portuguese",
               "it": "Italian", "ar": "Arabic", "hi": "Hindi"}
AUTO = "auto"


@dataclass
class Status:
    level: str = "warn"   # "ok" | "warn" | "error" → colour of the dot
    text: str = ""        # short, shown next to the dot
    detail: str = ""      # longer, shown as the tooltip


@dataclass
class Utterance:
    """One spoken or typed line. Emit it again with the same id to update it."""
    id: int
    source: str                    # "speaker" (other players) | "mic" | "typed"
    original: str = ""
    translation: str = ""
    src_lang: str = ""
    dst_lang: str = ""
    speaker: int = 0               # 1, 2, 3… for "speaker" lines; 0 = unknown
    final: bool = False            # False while the person is still talking
    latency_ms: int | None = None
    sent: bool | None = None       # chatbox: True sent, False failed, None not sent (yet)
    note: str = ""                 # e.g. "cut to 144 characters"
    dst_lang2: str = ""            # optional second microphone translation, captured per utterance
    translation2: str = ""
    panel_targets: tuple[str, ...] = ()
    panel_translations: tuple[tuple[str, str], ...] = ()


class Backend(QObject):
    status_changed = Signal(object)   # Status
    mic_level = Signal(float)         # 0.0 – 1.0
    speaker_level = Signal(float)     # 0.0 – 1.0
    utterance = Signal(object)        # Utterance
    setting_switched = Signal(str, str)   # (setting_name, new_value) when auto-switched
    switch_prompt_requested = Signal(str, str, str)  # (category, failed_service, reason)
    current_translating_model: str = ""
    current_translating_service: str = ""
    current_hearing_model: str = ""
    current_hearing_service: str = ""

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def apply_settings(self, settings) -> None:
        """Called at start and after every change in the window (ui.config.Settings)."""

    def target_lang(self) -> str:
        """The language typed text would be translated into right now (shown on the Send button)."""
        return "en"

    def speech_target_lang(self) -> str:
        """The language my microphone is translated into, independent of the Send menu."""
        return "en"

    def send_text(self, text: str) -> None:
        """Translate typed text and send it to the chatbox; answer with a "typed" Utterance."""
