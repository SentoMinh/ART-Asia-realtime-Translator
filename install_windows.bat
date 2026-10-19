@echo off
setlocal
title VRChat Translator - Windows setup
set "VRCT_SETUP_FILE=%~f0"
set "VRCT_SETUP_CHECK=%~1"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$s = [IO.File]::ReadAllText($env:VRCT_SETUP_FILE); & ([scriptblock]::Create(($s -split '(?m)^# POWERSHELL_START\r?$', 2)[1]))"
set "setup_result=%errorlevel%"
if /i not "%~1"=="--check" pause
exit /b %setup_result%
# POWERSHELL_START
$ErrorActionPreference = 'Stop'
$downloadDirectory = $null
try {
    Write-Host 'VRChat Translator - setup for the packaged EXE'
    Write-Host 'Python and app libraries are already included in the release EXE.'
    Write-Host ''
    $os = Get-CimInstance Win32_OperatingSystem
    $build = [int]$os.BuildNumber
    if (-not [Environment]::Is64BitOperatingSystem -or $build -lt 17763 -or $os.ProductType -ne 1) {
        throw 'This release requires 64-bit Windows 10 version 1809 or newer, or Windows 11.'
    }
    $architecture = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
    if ($architecture -ne 'AMD64') {
        throw 'This setup supports Intel/AMD x64 PCs. Windows on ARM has not been verified.'
    }
    Write-Host ('Detected: {0} (build {1}, x64)' -f $os.Caption, $build)
    if ($build -lt 22000) {
        Write-Host 'Windows 10: speaker capture may include other apps on the default audio output.' -ForegroundColor Yellow
        Write-Host 'Installing dependencies cannot add VRChat-only audio capture to Windows 10.'
    }
    if ($env:VRCT_SETUP_CHECK -eq '--check') {
        Write-Host 'Compatibility precheck passed. No downloads or installations performed.'
        Write-Host 'This precheck does not test the app or its audio capture.'
        exit 0
    }
    if ($env:VRCT_SETUP_CHECK) { throw 'Unknown option. Use no arguments to install, or --check for a read-only precheck.' }

    Write-Host ''
    Write-Host 'Downloading Microsoft Visual C++ v14 Redistributable (x64)...'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $downloadDirectory = Join-Path ([IO.Path]::GetTempPath()) ('VRCT-setup-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $downloadDirectory | Out-Null
    $installer = Join-Path $downloadDirectory 'vc_redist.x64.exe'
    Invoke-WebRequest -UseBasicParsing -Uri 'https://aka.ms/vc14/vc_redist.x64.exe' -OutFile $installer -TimeoutSec 180
    $signature = Get-AuthenticodeSignature -LiteralPath $installer
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch '(^|,\s*)O=Microsoft Corporation(,|$)') {
        throw 'The downloaded installer does not have a valid Microsoft signature. Installation stopped.'
    }
    Write-Host 'Installing the Microsoft runtime. Accept the Windows administrator prompt if shown.'
    $process = Start-Process -FilePath $installer -ArgumentList '/install', '/passive', '/norestart' -Verb RunAs -WindowStyle Hidden -Wait -PassThru
    switch ($process.ExitCode) {
        0 { Write-Host 'Microsoft runtime installed successfully.' }
        1638 { Write-Host 'A newer Microsoft runtime is already installed.' }
        3010 { Write-Host 'Microsoft runtime installed. Restart Windows before running the app.' -ForegroundColor Yellow }
        default { throw ('Microsoft runtime installation failed (exit code {0}). Try again after restarting Windows.' -f $process.ExitCode) }
    }
    Write-Host ''
    Write-Host 'Setup complete. Open your VRChat-Translator EXE.'
    Write-Host 'In the app, configure your provider API key or Custom domain URL and key.'
    Write-Host 'In VRChat, enable OSC from the action menu to use the chatbox.'
    Write-Host 'Allow microphone access in Windows Settings if microphone capture is blocked.'
    Write-Host 'An internet connection is required for online translation.'
    exit 0
} catch {
    Write-Host ('Setup failed: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'Check your internet connection and accept the administrator prompt when installing.'
    exit 1
} finally {
    if ($downloadDirectory -and (Test-Path -LiteralPath $downloadDirectory)) {
        # Delete only this invocation''s installer, then its empty temporary folder.
        Remove-Item -LiteralPath (Join-Path $downloadDirectory 'vc_redist.x64.exe') -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $downloadDirectory -ErrorAction SilentlyContinue
    }
}
