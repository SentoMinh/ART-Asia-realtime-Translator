"""Draw what the wearer would see: the panel on a raised wrist, from an orbiting view.

    python tools/preview_wrist.py [out_dir] [--hand left|right] [--width N] [--along N]
                                  [--out N] [--up N] [--tilt N] [--yaw N] [--roll N]
                                  [--font N] [--backdrop N]

A drawing, not a capture from SteamVR: the hand model by omoideshabou is rendered in
`vr.arm_preview`, and the panel is placed with the same maths the program gives SteamVR
(`vr.pose`), so moving a setting here moves the panel the way it would move in the headset.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtGui import QColor, QFont, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from tools.snapshot_vr import demo_panel  # noqa: E402
from vr.arm_preview import DEFAULT_YAW, DEFAULT_PITCH, draw  # noqa: E402
from vr.config import VrSettings  # noqa: E402

PICTURE = (1280, 800)


def main() -> None:
    defaults = VrSettings()
    parser = argparse.ArgumentParser()
    parser.add_argument("out_dir", nargs="?", default=".")
    parser.add_argument("--hand", default=defaults.hand, choices=["left", "right"])
    for name, setting in (("width", "width_cm"), ("along", "along_cm"), ("out", "out_cm"),
                          ("up", "up_cm"), ("tilt", "tilt_deg"), ("font", "font_px"),
                          ("yaw", "yaw_deg"), ("roll", "roll_deg"),
                          ("backdrop", "backdrop")):
        parser.add_argument(f"--{name}", dest=setting, type=int, default=getattr(defaults, setting))
    args = parser.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    settings = VrSettings(**{name: value for name, value in vars(args).items()
                             if name != "out_dir"}).clean()

    app = QApplication(sys.argv)
    panel, _wrist = demo_panel(app, settings)
    picture = draw(settings, panel.image(), size=PICTURE,
                   yaw_deg=DEFAULT_YAW, pitch_deg=DEFAULT_PITCH)
    painter = QPainter(picture)
    painter.setPen(QColor(255, 255, 255, 200))
    painter.setFont(QFont("Segoe UI", 13))
    painter.drawText(
        24, PICTURE[1] - 22,
        f"{settings.hand} wrist · {settings.width_cm} cm wide · along the arm {settings.along_cm} cm · "
        f"off {settings.out_cm} cm · up {settings.up_cm} cm · rotation {settings.tilt_deg}° / {settings.yaw_deg}° / {settings.roll_deg}°   "
        f"(a drawing from the placement maths, not a headset capture)")
    painter.end()
    target = out / f"wrist_on_{settings.hand}_hand.png"
    picture.save(str(target))
    print("saved", target.resolve())


if __name__ == "__main__":
    main()
