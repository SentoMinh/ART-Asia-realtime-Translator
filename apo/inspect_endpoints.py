"""Read-only capture-endpoint effects audit. Does not attach or register an APO."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import winreg

ROOT = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Capture"
FX_GUID = "{d04e05a6-594b-4fb6-a80d-01af5eed7d1d}"
SLOTS = {f"{FX_GUID},{number}": name for number, name in
         ((1, "legacy_pre"), (2, "legacy_post"), (5, "stream"), (6, "mode"), (7, "endpoint"),
          (13, "composite_stream"), (14, "composite_mode"), (15, "composite_endpoint"))}
FRIENDLY_NAME = "{a45c254e-df1c-4efd-8020-67d146a850e0},14"
DISABLED_FX = "{1da5d803-d492-4edd-8c23-e0c0ffee7f0e},5"


def component_details(effects):
    """Resolve indirect effect-pack references without changing any registry value."""
    found = []
    seen = set()
    for value in effects.values():
        for reference in value if isinstance(value, list) else [value]:
            if not isinstance(reference, str) or not reference.upper().startswith("SWD\\DRIVERENUM\\"):
                continue
            if reference.casefold() in seen:
                continue
            seen.add(reference.casefold())
            item = {"instance_id": reference}
            try:
                device = values("SYSTEM\\CurrentControlSet\\Enum\\" + reference)
                item["description"] = device.get("devicedesc", "").rsplit(";", 1)[-1]
                driver = device.get("driver")
                if driver:
                    package = values("SYSTEM\\CurrentControlSet\\Control\\Class\\" + driver)
                    item.update({key: package.get(key) for key in
                                 ("providername", "driverdesc", "driverversion", "infpath")})
            except OSError as error:
                item["error"] = str(error)
            found.append(item)
    return found


def values(path):
    result = {}
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
        index = 0
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, index)
            except OSError as error:
                if error.winerror == 259: break
                raise
            result[name.lower()] = value
            index += 1
    return result


def inspect():
    names = []
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, ROOT, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
        index = 0
        while True:
            try: names.append(winreg.EnumKey(key, index))
            except OSError as error:
                if error.winerror == 259: break
                raise
            index += 1
    result = []
    for name in names:
        item = {"endpoint_id": "{0.0.1.00000000}." + name}
        try:
            base = ROOT + "\\" + name
            item["device_state"] = values(base).get("devicestate")
            props = values(base + r"\Properties")
            item["name"] = props.get(FRIENDLY_NAME) or " - ".join(str(value) for value in (
                props.get("{a45c254e-df1c-4efd-8020-67d146a850e0},2"),
                props.get("{b3f8fa53-0004-438e-9003-51a46e139bfc},6")) if value) or name
            try: effects = values(base + r"\FxProperties")
            except FileNotFoundError: effects = {}
            item["existing_effects"] = {slot: effects[key] for key, slot in SLOTS.items() if key in effects}
            item["other_effect_property_keys"] = sorted(key for key in effects if key not in SLOTS)
            item["effect_components"] = component_details(effects)
            item["effects_disabled"] = effects.get(DISABLED_FX, props.get(DISABLED_FX))
            item["attachment_review"] = "Existing effects/configuration must be preserved; do not overwrite." if effects else "No endpoint effect properties found; this does not prove APO compatibility."
        except OSError as error:
            item["error"] = str(error)
        result.append(item)
    return {"read_only": True, "endpoints": result}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = inspect()
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    for item in report["endpoints"]:
        print(item.get("name", item["endpoint_id"]), "state=" + str(item.get("device_state")),
              "effects=" + ",".join(item.get("existing_effects", {})), item.get("error", ""))
