@echo off
setlocal
title Remove VRChat Translator Microphone Mixer
echo This removes our mixer from the microphone and briefly restarts Windows audio.
echo Windows will ask for administrator approval. Voice Clarity is preserved.
echo.
echo Press any key to continue, or close this window to cancel.
pause >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0remove_mixer.ps1"
echo.
pause
endlocal
