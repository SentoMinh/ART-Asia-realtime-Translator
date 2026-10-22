"""Build a transferable NLLB package from the app's verified local cache.

    python tools/package_nllb_offline.py --output dist/ART-NLLB-200-CT2-offline.zip
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
README = r"""ART - NLLB offline installation (Windows)

1. Download this ZIP on a connection that works, or receive it through USB/file transfer.
2. Close ART. Right-click the ZIP and Extract All before running anything inside it.
3. Double-click Install-NLLB.cmd. No administrator, Python, API key or internet is required.
4. Open ART > Settings > Models. Select Local Model for Translating.
   In Local Model > Set up, NLLB should show Ready; click Use model if needed.

The installer verifies all four files, copies them into your Windows user profile,
and verifies the copies. Existing matching files are kept. If different files are
replaced, the old folder is preserved as nllb-backup-... in the model cache.
Target: %LOCALAPPDATA%\VRChat-Translator\local-model\nllb
If copying fails, close ART and try again; keep the error message for diagnosis.

This is the exact pinned CPU INT8 model used by ART v0.12.3. An existing ART build
with NLLB support is required. This package contains model files, not the app.
Installation and local translation never contact Hugging Face. Obtaining the ZIP
still requires a working download or file-transfer route; no mainland-China network
has been tested. Keep the ZIP intact when sharing it and include its attribution.

The model is CC BY-NC 4.0 (noncommercial); see ATTRIBUTION.txt.
"""
ATTRIBUTION = """NLLB-200 distilled 600M by Meta AI / the NLLB Team.
Original model: https://huggingface.co/facebook/nllb-200-distilled-600M
Paper: No Language Left Behind: Scaling Human-Centered Machine Translation (2022).
https://arxiv.org/abs/2207.04672

CTranslate2 INT8 distribution: mijuanlo/nllb-200-distilled-600M-ct2-int8
https://huggingface.co/mijuanlo/nllb-200-distilled-600M-ct2-int8/tree/16bc5ff0482f9f1c0d35bdef950721ce58640789
License: Creative Commons Attribution-NonCommercial 4.0 International.
https://creativecommons.org/licenses/by-nc/4.0/
https://creativecommons.org/licenses/by-nc/4.0/legalcode

ART repackages the four required files byte-for-byte from that pinned revision;
no weights or tokenizers were changed. Only installation scripts and checksums
were added. No endorsement by the model authors is implied. No warranties are given.
The model license is separate from the application's code license.
"""
LAUNCHER = r'''@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-NLLB.ps1"
if errorlevel 1 (
    echo Installation failed. Keep the error above and try again after closing ART.
    pause
    exit /b 1
)
pause
'''


def package(model_dir: Path, output: Path) -> None:
    parts = json.loads((ROOT / 'engine/assets/local_models.json').read_text(encoding='utf-8'))['nllb-200-ct2']
    if output.exists():
        raise FileExistsError(f'Refusing to overwrite an existing package: {output}')
    manifest = []
    for part in parts:
        name = Path(part['place']).name
        source = model_dir / name
        with source.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if source.stat().st_size != part['size'] or digest != part['sha256']:
            raise ValueError(f'{name} does not match the pinned model')
        manifest.append(dict(name=name, size=part['size'], sha256=part['sha256']))
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for part in manifest:
            archive.write(model_dir / part['name'], 'nllb/' + part['name'])
        archive.writestr('model-files.json', json.dumps(manifest, indent=2))
        archive.write(ROOT / 'tools/install_nllb_offline.ps1', 'Install-NLLB.ps1')
        archive.writestr('Install-NLLB.cmd', LAUNCHER.replace('\n', '\r\n'))
        archive.writestr('README.txt', README)
        archive.writestr('ATTRIBUTION.txt', ATTRIBUTION)
    with output.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    output.with_suffix('.zip.sha256').write_text(f'{digest}  {output.name}\n', encoding='utf-8')
    print(f'{output} ({output.stat().st_size / 2**20:.1f} MiB)\nSHA-256: {digest}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', type=Path, default=Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'VRChat-Translator/local-model/nllb')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    package(args.model_dir, args.output)
