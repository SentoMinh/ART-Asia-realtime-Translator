# Builds the program.
#
#   pwsh -File tools\build.ps1             one file:  dist\VRChat-Translator-<version>.exe
#   pwsh -File tools\build.ps1 -Folder     a folder:  dist\VRChat-Translator\ and a zip of it
#                                          (starts a few seconds faster than the one-file program)
#   -DistPath dist\next                    build beside a copy of the program that is running
#   -Python <path to python.exe>           another environment than .venv-app
#
# The program carries the local runtimes (faster-whisper, sherpa-onnx, CTranslate2).
# Model weights and Whisper's cuBLAS files are downloaded separately in Settings.
# PyAV, NVIDIA's Python packages and PyTorch stay out of the program file.

param([switch]$Folder, [string]$DistPath = "dist", [string]$Python = "", [string]$MixerBuild = "", [string]$WhisperBuild = "")

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$py = if ($Python) { $Python } else { Join-Path $root ".venv-app\Scripts\python.exe" }
$version = (& $py -c "import ui; print(ui.__version__)").Trim()
$name = "VRChat-Translator"
$shape = if ($Folder) { "--onedir" } else { "--onefile" }
$mixerArgs = @()
$whisperDir = if ($WhisperBuild) { $WhisperBuild } else { Join-Path $root 'assets/whisper-vulkan' }
$whisperDll = Join-Path $whisperDir 'art_whisper_vulkan.dll'
if (!(Test-Path -LiteralPath $whisperDll)) { throw 'Build the Vulkan runtime first with tools/build-whisper-vulkan.ps1, or pass -WhisperBuild.' }
$whisperLicense = Join-Path $whisperDir 'whisper.cpp-LICENSE.txt'
if (!(Test-Path -LiteralPath $whisperLicense)) { throw 'Missing whisper.cpp license in the runtime folder.' }
$mixerArgs += @('--add-binary', "$whisperDll;assets/whisper-vulkan", '--add-data', "$whisperLicense;assets/whisper-vulkan")
if ($MixerBuild) {
    foreach ($dll in @('VrctMicApo.dll', 'VrctApoProducer.dll')) {
        $nativeFile = Join-Path $MixerBuild $dll
        if (!(Test-Path -LiteralPath $nativeFile)) { throw "Missing microphone mixer: $dll" }
        $mixerArgs += @('--add-binary', "$nativeFile;assets/apo")
    }
}

& $py -m PyInstaller app.py --noconfirm --clean --windowed $shape --name $name @mixerArgs `
    --distpath $DistPath --workpath build --specpath build `
    --icon "$root\assets\icon.ico" `
    --add-data "$root\engine\assets;engine\assets" --add-data "$root\assets\icon.ico;assets" --add-data "$root\assets\icon.png;assets" `
    --add-data "$root\assets\vr;assets\vr" --add-data "$root\assets\hand;assets\hand" `
    --collect-data zhconv --collect-data certifi `
    --collect-binaries sounddevice --collect-data _sounddevice_data `
    --collect-all pyaudiowpatch `
    --collect-binaries soxr --collect-binaries onnxruntime `
    --collect-binaries openvr `
    --hidden-import proctap._native --hidden-import engine.speech --hidden-import engine.translators `
    --collect-all sherpa_onnx --collect-all tokenizers --collect-all ctranslate2 --collect-binaries llama_cpp `
    --hidden-import engine.local_inference --hidden-import engine.local_model --hidden-import ui.local_download --hidden-import ui.switch_dialog `
    --hidden-import http.client --hidden-import queue `
    --exclude-module av --exclude-module hf_xet `
    --exclude-module scipy --exclude-module nvidia --exclude-module torch `
    --exclude-module pytest --exclude-module tkinter `
    --exclude-module openvr.glframework --exclude-module openvr.gl_renderer `
    --exclude-module openvr.color_cube_actor --exclude-module openvr.tracked_devices_actor `
    --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets `
    --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQml --exclude-module PySide6.Qt3DCore `
    --exclude-module PySide6.QtMultimedia --exclude-module PySide6.QtPdf --exclude-module PySide6.QtCharts
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

New-Item -ItemType Directory -Force (Join-Path $root "dist") | Out-Null
if ($Folder) {
    $out = Join-Path $root "dist\$name-$version-win64.zip"
    if (Test-Path $out) { Remove-Item $out }
    Compress-Archive -Path (Join-Path $root "$DistPath\$name") -DestinationPath $out -CompressionLevel Optimal
} else {
    $out = Join-Path $root "dist\$name-$version.exe"
    Copy-Item (Join-Path $root "$DistPath\$name.exe") $out -Force
}
"{0}  {1:N0} MB" -f $out, ((Get-Item $out).Length / 1MB)
