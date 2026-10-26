"""Wrist settings in %APPDATA%\\VRChat-Translator\\vr.json, preserving existing VR placements."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

HANDS = {"left": "Left hand", "right": "Right hand"}
WIDTH_RANGE = (10, 50)      # cm
ALONG_RANGE = (-10, 30)     # cm from the controller towards the elbow
OUT_RANGE = (0, 25)         # cm away from the arm
UP_RANGE = (-15, 15)        # cm
TILT_RANGE = (-90, 90)      # degrees around the arm
ROTATION_RANGE = (-180, 180)  # degrees around the panel's up and facing axes
OPACITY_RANGE = (20, 100)   # percent
FONT_RANGE = (14, 40)       # px on a panel 720 px wide
BACKDROP_RANGE = (0, 100)   # percent


def default_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "VRChat-Translator" / "vr.json"


@dataclass
class VrSettings:
    enabled: bool = True
    hand: str = "left"
    look_only: bool = True     # the panel shows only while its wearer looks at it
    width_cm: int = 24
    along_cm: int = 12
    out_cm: int = 6
    up_cm: int = 0
    tilt_deg: int = 0
    yaw_deg: int = 0
    roll_deg: int = 0
    opacity: int = 95
    font_px: int = 24
    backdrop: int = 80         # darkness of the panel behind the text

    def clean(self) -> "VrSettings":
        if self.hand not in HANDS:
            self.hand = "left"
        for name, (low, high) in (("width_cm", WIDTH_RANGE), ("along_cm", ALONG_RANGE),
                                  ("out_cm", OUT_RANGE), ("up_cm", UP_RANGE),
                                  ("tilt_deg", TILT_RANGE), ("opacity", OPACITY_RANGE),
                                  ("yaw_deg", ROTATION_RANGE), ("roll_deg", ROTATION_RANGE),
                                  ("font_px", FONT_RANGE), ("backdrop", BACKDROP_RANGE)):
            setattr(self, name, min(max(int(getattr(self, name)), low), high))
        return self


def load(path: Path | None = None) -> VrSettings:
    path = path or default_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return VrSettings()
    if not isinstance(data, dict):
        return VrSettings()
    defaults = VrSettings()
    # a wrong type in the file (edited by hand) falls back to the default
    picked = {f.name: data[f.name] for f in fields(VrSettings)
              if f.name in data and type(data[f.name]) is type(getattr(defaults, f.name))}
    return VrSettings(**picked).clean()


def save(settings: VrSettings, path: Path | None = None) -> None:
    path = path or default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
    tmp.replace(path)
