"""Window settings, kept in %APPDATA%\\VRChat-Translator\\ui.json."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from engine import services   # who can hear and translate ("local" = Whisper on this PC)

from .backend import AUTO, LANGS
from .i18n import UI_LANGS

FONT_RANGE = (12, 32)
BACKDROP_RANGE = (0, 100)
MIN_SIZE = (440, 220)
VAD_RANGE = (0.3, 0.9)    # how sure the voice detector must be that someone talks


def default_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "VRChat-Translator" / "ui.json"


@dataclass
class Settings:
    my_lang: str = "vi"            # my spoken language and the target for other players' subtitles
    their_lang: str = AUTO          # their spoken language and my mic's target; AUTO = detect theirs
    their_lang2: str = ""           # optional second microphone translation target
    send_lang: str = AUTO           # typed text is translated into this; AUTO = the language heard last
    ui_lang: str = "en"             # language of the window itself: en | zh | vi
    mic_on: bool = True             # my mic → chatbox
    mic_device: str = ""            # microphone name; "" = the Windows default
    speaker_device: str = ""        # output device name; "" = VRChat process audio
    subtitles_on: bool = True       # other players → chat log
    vad_on: bool = True             # voice detector
    vad_sensitivity: float = 0.7    # how sure the detector must be that it hears a voice (other players)
    mic_vad_sensitivity: float = 0.5   # the same for my own microphone
    # speech → text: an online service, or "local" (Whisper on this PC); text → text: an online
    # service. New profiles start with Custom domain; add-ons are fallback translators.
    hearing: str = field(default_factory=services.default_service)
    translating: str = field(default_factory=services.default_service)
    show_original: bool = True      # show the heard text above its translation
    font_px: int = 17
    backdrop: int = 85              # percent; 0 = only the text floats over the game
    always_on_top: bool = True
    auto_hide_bars: bool = False    # only the chat log stays while the mouse is away
    chatbox_typing: bool = True     # show the "typing" dots in VRChat while I talk
    chatbox_original: bool = False  # chatbox gets "translation (original)"
    chatbox_speaker: bool = False   # also send other players' translation and original to my chatbox
    x: int = -1
    y: int = -1
    w: int = 560
    h: int = 460

    def clean(self) -> "Settings":
        self.hearing = services.migrate_provider(self.hearing)
        self.translating = services.migrate_provider(self.translating)
        if self.hearing == "dev" or self.translating == "dev":
            services.migrate_legacy_settings()
            if self.hearing == "dev":
                self.hearing = "custom"
            if self.translating == "dev":
                self.translating = "custom"
        if self.my_lang not in LANGS:
            self.my_lang = "vi"
        if self.their_lang != AUTO and self.their_lang not in LANGS:
            self.their_lang = AUTO
        if self.their_lang2 not in LANGS or self.their_lang2 == self.their_lang:
            self.their_lang2 = ""
        if self.send_lang != AUTO and self.send_lang not in LANGS:
            self.send_lang = AUTO
        if self.ui_lang not in UI_LANGS:
            self.ui_lang = "en"
        if self.hearing not in services.offered(services.HEARING):
            self.hearing = services.default_service()
        if self.translating not in services.offered(services.TRANSLATING):
            self.translating = services.default_service()
        self.vad_sensitivity = min(max(float(self.vad_sensitivity), VAD_RANGE[0]), VAD_RANGE[1])
        self.mic_vad_sensitivity = min(max(float(self.mic_vad_sensitivity), VAD_RANGE[0]), VAD_RANGE[1])
        self.font_px = min(max(int(self.font_px), FONT_RANGE[0]), FONT_RANGE[1])
        self.backdrop = min(max(int(self.backdrop), BACKDROP_RANGE[0]), BACKDROP_RANGE[1])
        self.w = max(int(self.w), MIN_SIZE[0])
        self.h = max(int(self.h), MIN_SIZE[1])
        return self


def load(path: Path | None = None) -> Settings:
    path = path or default_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    if not isinstance(data, dict):
        return Settings()
    names = {f.name for f in fields(Settings)}
    defaults = Settings()
    picked = {}
    if data.get("stt_engine") == "local" and "hearing" not in data:
        picked["hearing"] = "local"     # saved by version 0.9.7 or older
    for name, value in data.items():
        # a wrong type in the file (edited by hand) falls back to the default
        if name in names and type(value) is type(getattr(defaults, name)):
            picked[name] = value
    return Settings(**picked).clean()


def save(settings: Settings, path: Path | None = None) -> None:
    path = path or default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
    tmp.replace(path)
