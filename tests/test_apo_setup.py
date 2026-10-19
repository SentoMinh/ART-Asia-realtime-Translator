from copy import deepcopy
from pathlib import Path

import pytest

from vrc import apo_setup as setup

ENDPOINT = "{62b52006-a33c-453d-844f-8a1ece251538}"
BASE = setup.CAPTURE + "\\" + ENDPOINT
EFFECTS = BASE + r"\FxProperties"


class Registry:
    def __init__(self):
        self.data = {(BASE, "DeviceState"): {"kind": 4, "data": 1},
                     (EFFECTS, "voice-clarity-reference"): {"kind": 1, "data": "existing component"}}
        self.fail_at = None
        self.writes = 0

    def exists(self, path):
        return path == EFFECTS or any(key[0] == path for key in self.data)

    def read(self, path, name):
        return deepcopy(self.data.get((path, name)))

    def write(self, path, name, value):
        self.writes += 1
        if self.writes == self.fail_at:
            raise OSError("injected registry error")
        if value is None:
            self.data.pop((path, name), None)
        else:
            self.data[path, name] = deepcopy(value)

    def delete_empty(self, path): pass


def plan(registry):
    return setup.make_plan(registry, ENDPOINT, "S-1-5-21-1-2-3-1001", Path("C:/fixture"))


def test_install_remove_preserves_existing_effects_exactly():
    registry = Registry()
    before = deepcopy(registry.data)
    state = plan(registry)
    saved = []
    setup.apply(registry, state, lambda value: saved.append(deepcopy(value)))
    assert saved[0]["phase"] == "installing"
    assert registry.read(EFFECTS, setup.FX + ",5")["data"] == setup.CLSID
    setup.restore(registry, state, lambda value: saved.append(deepcopy(value)))
    assert state["phase"] == "removed"
    assert registry.data == before


@pytest.mark.parametrize("failure", [1, 5, 17, 19])
def test_partial_install_rolls_back(failure):
    registry = Registry()
    before = deepcopy(registry.data)
    registry.fail_at = failure
    state = plan(registry)
    with pytest.raises(OSError, match="injected"):
        setup.apply(registry, state, lambda _: None)
    assert registry.data == before
    assert state["phase"] == "removed"


def test_changes_made_by_someone_else_after_install_are_preserved():
    registry = Registry()
    state = plan(registry)
    setup.apply(registry, state, lambda _: None)
    other = {"kind": 1, "data": "somebody else's new effect"}
    registry.write(EFFECTS, setup.FX + ",5", other)
    with pytest.raises(RuntimeError, match="preserved"):
        setup.restore(registry, state, lambda _: None)
    assert registry.read(EFFECTS, setup.FX + ",5") == other
    assert state["phase"] == "restore_conflict"


@pytest.mark.parametrize("number", [1, 2, 5, 7, 13, 15])
def test_existing_stream_or_endpoint_effect_is_never_replaced(number):
    registry = Registry()
    registry.write(EFFECTS, setup.FX + f",{number}", {"kind": 1, "data": "existing"})
    before = deepcopy(registry.data)
    with pytest.raises(RuntimeError, match="effects"):
        plan(registry)
    assert registry.data == before


@pytest.mark.parametrize("slot", ["stream", "legacy"])
def test_both_journal_slots_restore_exact_original_values(slot):
    registry = Registry()
    before = deepcopy(registry.data)
    state = setup.make_plan(registry, ENDPOINT, "sid", setup.INSTALL, effect_slot=slot)
    assert setup.validate_journal(state) is state
    setup.apply(registry, state, lambda _: None)
    setup.restore(registry, state, lambda _: None)
    assert registry.data == before


def test_legacy_journal_cannot_restore_stream_or_unrelated_values():
    state = setup.make_plan(Registry(), ENDPOINT, "sid", setup.INSTALL, effect_slot="legacy")
    state["changes"][-1]["name"] = setup.FX + ",5"
    with pytest.raises(RuntimeError, match="Unexpected"):
        setup.validate_journal(state)


@pytest.mark.parametrize("results, expected", [([True], "stream"), ([False, True], "legacy"), ([False, False], None)])
def test_live_validation_fallback_and_full_rollback(monkeypatch, results, expected):
    registry = Registry()
    before = deepcopy(registry.data)
    state = plan(registry)
    state.update(hashes={}, microphone="Headset")
    outcomes = iter(results)
    slots = []
    saved = []
    monkeypatch.setattr(setup, "save_state", lambda value: saved.append(deepcopy(value)))
    monkeypatch.setattr(setup, "restart_audio", lambda: None)
    def validate(state, microphone):
        slots.append(state["effect_slot"])
        return next(outcomes)
    monkeypatch.setattr(setup, "validate_capture", validate)
    if expected:
        installed = setup.activate_attachment(registry, state, "Headset", restart=True)
        assert installed["phase"] == "validated" and installed["effect_slot"] == expected
        setup.restore(registry, installed, lambda _: None)
    else:
        with pytest.raises(RuntimeError, match="rolled back"):
            setup.activate_attachment(registry, state, "Headset", restart=True)
        assert saved[-1]["phase"] == "removed"
    assert registry.data == before
    assert slots == (["stream"] if len(results) == 1 else ["stream", "legacy"])
