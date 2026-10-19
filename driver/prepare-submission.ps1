param(
    [Parameter(Mandatory=$true)][string]$DriverPackage,
    [Parameter(Mandatory=$true)][string]$Symbols,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$source = (Resolve-Path -LiteralPath $DriverPackage).Path
$symbolsFile = (Resolve-Path -LiteralPath $Symbols).Path
$output = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) { throw 'Choose a new submission output directory.' }
New-Item -ItemType Directory -Path $output | Out-Null
$package = Join-Path $output 'VrctAudio'
New-Item -ItemType Directory -Path $package | Out-Null
foreach ($name in @('VrctAudio.sys', 'VrctAudio.inf', 'VrctAudio.cat')) {
    Copy-Item -LiteralPath (Join-Path $source $name) -Destination $package
}
Copy-Item -LiteralPath $symbolsFile -Destination (Join-Path $package 'VrctAudio.pdb')
Copy-Item -LiteralPath (Join-Path $source 'MICROSOFT-LICENSE') -Destination $output
$infverif = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\Tools\10.0.26100.0\x64\InfVerif.exe'
& $infverif /u (Join-Path $package 'VrctAudio.inf')
if ($LASTEXITCODE -ne 0) { throw 'INF verification failed.' }
# All source paths are relative to this new staging folder. No file is at the CAB root.
$ddf = @'
.OPTION EXPLICIT
.Set CabinetNameTemplate=VrctAudio-submission.cab
.Set DiskDirectoryTemplate=.
.Set Cabinet=on
.Set Compress=on
.Set CompressionType=MSZIP
.Set MaxDiskSize=0
.Set MaxCabinetSize=0
.Set DestinationDir=VrctAudio
VrctAudio\VrctAudio.inf
VrctAudio\VrctAudio.sys
VrctAudio\VrctAudio.cat
VrctAudio\VrctAudio.pdb
'@
Set-Content -LiteralPath (Join-Path $output 'submission.ddf') -Value $ddf -Encoding ascii
Push-Location -LiteralPath $output
try {
    & "$env:WINDIR\System32\makecab.exe" /f submission.ddf
    if ($LASTEXITCODE -ne 0) { throw 'CAB creation failed.' }
} finally { Pop-Location }
$cab = Join-Path $output 'VrctAudio-submission.cab'
if (!(Test-Path -LiteralPath $cab)) { throw 'Submission CAB was not produced.' }
$hashes = Get-ChildItem -LiteralPath $package -File | Get-FileHash -Algorithm SHA256
$hashes | Select-Object @{Name='File';Expression={[IO.Path]::GetFileName($_.Path)}},Hash |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $output 'submission-hashes.json') -Encoding utf8
Write-Host "Unsigned submission CAB: $cab"
Write-Host 'Use symbols from the same Release build. This CAB is not an installer and is not ready to upload until signed with your registered signing certificate.'
