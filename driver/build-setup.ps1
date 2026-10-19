param(
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$SignedPackage = ''
)
$ErrorActionPreference = 'Stop'
$output = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) { throw 'Choose a new output directory.' }
New-Item -ItemType Directory -Path $output | Out-Null
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$msbuild = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -find 'MSBuild\**\Bin\amd64\MSBuild.exe' | Select-Object -First 1
if (!$msbuild) { throw 'Visual Studio 2022 C++ Build Tools are required.' }
$extra = @()
if ($SignedPackage) {
    $source = (Resolve-Path -LiteralPath $SignedPackage).Path
    $package = Join-Path $output 'package'
    New-Item -ItemType Directory -Path $package | Out-Null
    foreach ($file in @('VrctAudio.sys', 'VrctAudio.inf', 'VrctAudio.cat', 'MICROSOFT-LICENSE')) {
        Copy-Item -LiteralPath (Join-Path $source $file) -Destination $package
    }
    $cat = Join-Path $package 'VrctAudio.cat'
    $signature = Get-AuthenticodeSignature -LiteralPath $cat
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch '(^|,\s*)CN=Microsoft Windows Hardware Compatibility Publisher(,|$)') {
        throw 'A valid Microsoft Hardware Compatibility Publisher catalog is required. Unsigned and test-signed packages cannot be bundled.'
    }
    $signtool = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe'
    foreach ($file in @('VrctAudio.sys', 'VrctAudio.inf')) {
        & $signtool verify /kp /v /c $cat (Join-Path $package $file)
        if ($LASTEXITCODE -ne 0) { throw "Kernel signing/catalog membership verification failed: $file" }
    }
    $resources = Join-Path $output 'package.rc'
    $lines = @('#include <windows.h>')
    $id = 201
    foreach ($file in @('VrctAudio.sys', 'VrctAudio.inf', 'VrctAudio.cat')) {
        $path = (Join-Path $package $file).Replace('\', '/')
        $lines += "$id RCDATA `"$path`""
        $id++
    }
    Set-Content -LiteralPath $resources -Value $lines -Encoding utf8
    Copy-Item -LiteralPath (Join-Path $package 'MICROSOFT-LICENSE') -Destination $output
    $extra += "/p:PackageResources=$resources"
}
& $msbuild (Join-Path $PSScriptRoot 'setup\setup.vcxproj') /m /t:Rebuild /p:Configuration=Release /p:Platform=x64 "/p:OutDir=$output\" "/p:IntDir=$output\obj\" @extra
if ($LASTEXITCODE -ne 0) { throw 'Setup build failed.' }
if ($SignedPackage) {
    Write-Host 'Setup built with verified Microsoft-signed payload. Sign the setup EXE and validate in clean Windows 10/11 VMs before publishing.'
} else {
    Write-Host 'Diagnostic setup built: --status is read-only; device installation/removal is disabled.'
}
