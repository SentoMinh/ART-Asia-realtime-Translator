@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv-app\Scripts\pythonw.exe" (
    echo The development Python environment is missing.
    pause
    exit /b 1
)
start "" ".venv-app\Scripts\pythonw.exe" "tools\preview_music.py"
endlocal
