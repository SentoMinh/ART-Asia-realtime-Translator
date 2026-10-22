"""The standalone Windows installer needs no network and preserves old models."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'tools/install_nllb_offline.ps1'
pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows PowerShell installer')


@pytest.fixture
def offline_package(tmp_path):
    package = tmp_path / 'package with spaces'
    (package / 'nllb').mkdir(parents=True)
    manifest = []
    for name in ('config.json', 'shared_vocabulary.json', 'tokenizer.json', 'model.bin'):
        data = ('test data for ' + name).encode()
        (package / 'nllb' / name).write_bytes(data)
        manifest.append(dict(name=name, size=len(data), sha256=hashlib.sha256(data).hexdigest()))
    (package / 'model-files.json').write_text(json.dumps(manifest), encoding='utf-8')
    return package


def install(package, cache):
    return subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                           '-File', str(SCRIPT), '-PackageRoot', str(package), '-CacheRoot', str(cache)],
                          capture_output=True, text=True, timeout=30,
                          creationflags=subprocess.CREATE_NO_WINDOW)


def test_install_and_repeat_keep_verified_model(offline_package, tmp_path):
    cache = tmp_path / 'cache with spaces'
    first = install(offline_package, cache)
    assert first.returncode == 0, first.stderr
    for source in (offline_package / 'nllb').iterdir():
        assert (cache / 'nllb' / source.name).read_bytes() == source.read_bytes()
    marker = cache / 'nllb' / 'keep.txt'
    marker.write_text('keep')
    again = install(offline_package, cache)
    assert again.returncode == 0 and 'already installed' in again.stdout
    assert marker.read_text() == 'keep'
    assert [p.name for p in cache.iterdir()] == ['nllb']


def test_replacement_preserves_entire_previous_folder(offline_package, tmp_path):
    cache = tmp_path / 'cache'
    (cache / 'nllb').mkdir(parents=True)
    (cache / 'nllb' / 'model.bin').write_bytes(b'old model')
    (cache / 'nllb' / 'other-file').write_bytes(b'keep this too')
    completed = install(offline_package, cache)
    assert completed.returncode == 0, completed.stderr
    backups = list(cache.glob('nllb-backup-*'))
    assert len(backups) == 1
    assert (backups[0] / 'model.bin').read_bytes() == b'old model'
    assert (backups[0] / 'other-file').read_bytes() == b'keep this too'


@pytest.mark.parametrize('damage', ['content', 'missing', 'traversal', 'duplicate'])
def test_bad_package_cannot_change_existing_model(offline_package, tmp_path, damage):
    cache = tmp_path / 'cache'
    (cache / 'nllb').mkdir(parents=True)
    existing = cache / 'nllb' / 'model.bin'
    existing.write_bytes(b'original')
    manifest_path = offline_package / 'model-files.json'
    manifest = json.loads(manifest_path.read_text())
    if damage == 'content':
        path = offline_package / 'nllb' / 'model.bin'
        path.write_bytes(b'X' * path.stat().st_size)
    elif damage == 'missing':
        (offline_package / 'nllb' / 'tokenizer.json').unlink()
    else:
        manifest[0]['name'] = '../escape' if damage == 'traversal' else 'model.bin'
        manifest_path.write_text(json.dumps(manifest))
    completed = install(offline_package, cache)
    assert completed.returncode != 0
    assert ('Damaged or missing file' if damage in ('content', 'missing') else 'Invalid model filenames') in completed.stderr
    assert existing.read_bytes() == b'original'
    assert [p.name for p in cache.iterdir()] == ['nllb']
