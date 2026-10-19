param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$output = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) { throw 'Use a new output directory.' }
New-Item -ItemType Directory -Path $output | Out-Null
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$msbuild = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -find 'MSBuild\**\Bin\amd64\MSBuild.exe' | Select-Object -First 1
if (!$msbuild) { throw 'Visual Studio 2022 C++ and ATL tools are required.' }
foreach ($project in @('apo','producer','tests','apo-test')) {
    $name = if ($project -eq 'apo-test') { 'apo' } else { $project }
    $extra = @()
    if ($project -eq 'apo-test') { $extra += '/p:ApoTesting=true' }
    & $msbuild (Join-Path $PSScriptRoot "$name.vcxproj") /m /t:Build /p:Configuration=Release /p:Platform=x64 "/p:OutDir=$output\" "/p:IntDir=$output\obj-$project\" @extra
    if ($LASTEXITCODE -ne 0) { throw "Build failed: $project" }
}
& (Join-Path $output 'ApoTests.exe') (Join-Path $output 'VrctMicApo-Test.dll') (Join-Path $output 'VrctApoProducer.dll')
if ($LASTEXITCODE -ne 0) { throw 'Standalone APO tests failed.' }
Write-Host 'Prototype built and standalone tests passed. No COM registration, microphone attachment, or Windows audio restart was performed.'
