# Developer build only. Users receive the runtime inside ART, and download weights in Settings.
param(
    [Parameter(Mandatory=$true)][string]$VulkanSdk,
    [string]$CMake = 'cmake',
    [string]$BuildDirectory = '.tools/wvk',
    [string]$OutputDirectory = 'assets/whisper-vulkan'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
if (!(Test-Path -LiteralPath (Join-Path $VulkanSdk 'Bin/glslc.exe'))) { throw 'A Vulkan SDK with glslc is required.' }
$env:VULKAN_SDK = [IO.Path]::GetFullPath($VulkanSdk)
& $CMake -S native/whisper_vulkan -B $BuildDirectory -G 'Visual Studio 17 2022' -A x64
if ($LASTEXITCODE -ne 0) { throw 'Whisper Vulkan configuration failed.' }
& $CMake --build $BuildDirectory --config Release --target art_whisper_vulkan --parallel 2
if ($LASTEXITCODE -ne 0) { throw 'Whisper Vulkan compilation failed.' }
New-Item -ItemType Directory -Force $OutputDirectory | Out-Null
Copy-Item -LiteralPath (Join-Path $BuildDirectory 'Release/art_whisper_vulkan.dll') -Destination $OutputDirectory
Copy-Item -LiteralPath (Join-Path $BuildDirectory 'whisper.cpp-LICENSE.txt') -Destination (Join-Path $OutputDirectory 'whisper.cpp-LICENSE.txt')
Write-Output 'Whisper Vulkan runtime built. No graphics drivers or model selections were changed.'
