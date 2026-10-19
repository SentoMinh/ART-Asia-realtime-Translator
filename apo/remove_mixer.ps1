$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv-app\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Run this from the development project.' }
$report = Join-Path $root '.tools\apo-remove-result.json'
if (Test-Path -LiteralPath $report) { Remove-Item -LiteralPath $report }
Write-Host 'Removing the microphone mixer. Windows audio will briefly restart.'
$arguments = '-m vrc.apo_setup remove --restart-audio --report "' + $report + '"'
$process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $root -Verb RunAs -WindowStyle Hidden -Wait -PassThru
if (Test-Path -LiteralPath $report) {
    Get-Content -LiteralPath $report
} else {
    throw 'Setup did not produce a result. Administrator approval may have been cancelled.'
}
if ($process.ExitCode -ne 0) { throw 'Removal did not finish. See the result above.' }
