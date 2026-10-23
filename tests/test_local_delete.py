from pathlib import Path

import pytest

from engine import local_model, services


@pytest.mark.parametrize("model", [*local_model.MODELS, *local_model.REMOVED_MODELS])
def test_delete_only_this_models_weights_and_partials(model):
    root = local_model.folder()
    owned = local_model._owned_files(model)
    for path in owned:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"model data")
    keep = [root / "gpu/cublas64_12.dll", root / "unrelated/model.bin",
            root / "downloading/some-other-model/model.bin", root / "whisper/notes.txt",
            root / "downloading" / local_model.PARTS[0].name]
    for path in keep:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"keep")
    services.save("local", hear_model="sensevoice", translate_model="nllb-200-ct2")
    settings = services.models_file().read_bytes()
    assert local_model.has_files(model)
    local_model.delete(model)
    assert not local_model.has_files(model)
    assert all(not path.exists() for path in owned)
    assert all(path.read_bytes() == b"keep" for path in keep)
    assert services.models_file().read_bytes() == settings
    local_model.delete(model)  # Repeating cleanup is harmless.


def test_delete_validates_all_targets_before_removing_anything(monkeypatch):
    root = local_model.folder()
    good = root / "nllb/config.json"
    good.parent.mkdir(parents=True)
    good.write_bytes(b"keep")
    outside = root.parent / "outside.bin"
    outside.write_bytes(b"keep")
    parts = (local_model.Part("https://test/config.json", 4, "", "nllb/config.json"),
             local_model.Part("https://test/outside.bin", 4, "", "nllb/../../outside.bin"))
    monkeypatch.setattr(local_model, "parts", lambda model: parts)
    with pytest.raises(local_model.DownloadError, match="nothing was deleted"):
        local_model.delete("nllb-200-ct2")
    assert good.read_bytes() == outside.read_bytes() == b"keep"


def test_delete_refuses_redirected_model_folder(monkeypatch):
    root = local_model.folder()
    source = root / "nllb/model.bin"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"keep")
    resolve = Path.resolve
    monkeypatch.setattr(Path, "resolve", lambda path, *a, **kw:
                        root / "sensevoice/model.bin" if path == source else resolve(path, *a, **kw))
    with pytest.raises(local_model.DownloadError, match="nothing was deleted"):
        local_model.delete("nllb-200-ct2")
    assert source.read_bytes() == b"keep"


def test_locked_file_reports_failure_and_keeps_file(monkeypatch):
    target = local_model.folder() / "nllb/model.bin"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"keep")
    unlink = Path.unlink
    def remove(path, **kwargs):
        if path == target:
            raise PermissionError("file in use")
        return unlink(path, **kwargs)
    monkeypatch.setattr(Path, "unlink", remove)
    with pytest.raises(local_model.DownloadError, match="Stop using the model"):
        local_model.delete("nllb-200-ct2")
    assert target.read_bytes() == b"keep"


def test_deleted_turbo_does_not_silently_redownload_from_external_cache(monkeypatch):
    monkeypatch.setattr(local_model, "installed", lambda model: True)
    monkeypatch.setattr(local_model, "nvidia_card", lambda: True)
    monkeypatch.setattr(local_model, "gpu_folders", lambda: ["CUDA"])
    assert local_model.missing("large-v3-turbo") == ""
    local_model.delete("large-v3-turbo")
    assert "not downloaded" in local_model.missing("large-v3-turbo")
    monkeypatch.setattr(local_model, "ready", lambda **kw: True)
    assert local_model.missing("large-v3-turbo") == ""
