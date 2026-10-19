"""Indirect effects must be visible before planning microphone attachment."""
import pytest

from apo import inspect_endpoints as audit


def test_indirect_effect_component_is_resolved_once(monkeypatch):
    reference = r"SWD\DRIVERENUM\fixture"
    paths = []

    def values(path):
        paths.append(path)
        if "\\Enum\\" in path:
            return {"devicedesc": "@oem4.inf,%name%;Voice Clarity", "driver": r"{fixture}\0000"}
        return {"providername": "Microsoft", "driverdesc": "Voice Clarity",
                "driverversion": "1.2.3", "infpath": "oem4.inf"}

    monkeypatch.setattr(audit, "values", values)
    result = audit.component_details({"indirect": reference, "duplicate": [reference], "unrelated": 1})
    assert len(result) == 1
    assert result[0]["description"] == "Voice Clarity"
    assert result[0]["providername"] == "Microsoft"
    assert len(paths) == 2


def test_unreadable_component_remains_visible(monkeypatch):
    def denied(_):
        raise PermissionError("Access denied")

    monkeypatch.setattr(audit, "values", denied)
    result = audit.component_details({"indirect": r"SWD\DRIVERENUM\fixture"})
    assert result[0]["error"] == "Access denied"


@pytest.mark.parametrize("number, name", [(13, "composite_stream"), (14, "composite_mode"), (15, "composite_endpoint")])
def test_composite_effect_slots(number, name):
    assert audit.SLOTS[f"{audit.FX_GUID},{number}"] == name
