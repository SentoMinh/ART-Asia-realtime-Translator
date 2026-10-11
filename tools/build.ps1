# Builds the program.
#
#   pwsh -File tools\build.ps1             one file:  dist\VRChat-Translator-<Friends|Public>-<version>.exe
#   pwsh -File tools\build.ps1 -Folder     a folder:  dist\VRChat-Translator\ and a zip of it
#                                          (starts a few seconds faster than the one-file program)
#   -DistPath dist\next                    build beside a copy of the program that is running
#   -Python <path to python.exe>           another environment than .venv-app
#
# The program hears through an online service (Settings → Models). "Local Model" is left out on purpose: it needs
# faster-whisper, CTranslate2 and 2 GB of NVIDIA libraries, so it stays in the source version
# (run_ui.bat). Leaving those out is also what makes a single file of about 80 MB possible.

param([switch]$Folder, [string]$DistPath = "dist", [string]$Python = "")

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$py = if ($Python) { $Python } else { Join-Path $root ".venv-app\Scripts\python.exe" }
$version = (& $py -c "import ui; print(ui.__version__)").Trim()
$edition = (& $py -c "from engine.services import dev; print('Friends' if dev() else 'Public')").Trim()
$name = "VRChat-Translator"
$shape = if ($Folder) { "--onedir" } else { "--onefile" }

& $py -m PyInstaller app.py --noconfirm --clean --windowed $shape --name $name `
    --distpath $DistPath --workpath build --specpath build `
    --icon "$root\assets\icon.ico" `
    --add-data "$root\engine\assets;engine\assets" --add-data "$root\assets;assets" `
    --collect-data zhconv --collect-data certifi `
    --collect-binaries sounddevice --collect-data _sounddevice_data `
    --collect-all pyaudiowpatch `
    --collect-binaries soxr --collect-binaries onnxruntime `
    --hidden-import proctap._native --hidden-import engine.speech --hidden-import engine.translators `
    --hidden-import http.client --hidden-import queue `
    --exclude-module faster_whisper --exclude-module ctranslate2 --exclude-module av `
    --exclude-module tokenizers --exclude-module huggingface_hub --exclude-module hf_xet `
    --exclude-module scipy --exclude-module nvidia --exclude-module torch `
    --exclude-module pytest --exclude-module tkinter `
    --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets `
    --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQml --exclude-module PySide6.Qt3DCore `
    --exclude-module PySide6.QtMultimedia --exclude-module PySide6.QtPdf --exclude-module PySide6.QtCharts
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

New-Item -ItemType Directory -Force (Join-Path $root "dist") | Out-Null
if ($Folder) {
    $out = Join-Path $root "dist\$name-$edition-$version-win64.zip"
    if (Test-Path $out) { Remove-Item $out }
    Compress-Archive -Path (Join-Path $root "$DistPath\$name") -DestinationPath $out -CompressionLevel Optimal
} else {
    $out = Join-Path $root "dist\$name-$edition-$version.exe"
    Copy-Item (Join-Path $root "$DistPath\$name.exe") $out -Force
}
"{0}  {1:N0} MB" -f $out, ((Get-Item $out).Length / 1MB)
