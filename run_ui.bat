@echo off
rem Opens the translator window with the app's own Python (.venv-app: PySide6, proc-tap,
rem sounddevice). Without it, the ai-translator one is used: the window works, without sound.
cd /d "%~dp0"
rem First look for a newer version on GitHub and install it (tools\update.py). Skipped when
rem offline or while files here are being edited;  set VRCT_NO_UPDATE=1  turns it off.
if exist .venv-app\Scripts\python.exe .venv-app\Scripts\python.exe tools\update.py
set PY=.venv-app\Scripts\pythonw.exe
"%PY%" -c "import PySide6" 2>nul || set PY=..\ai-translator\.venv\Scripts\pythonw.exe
rem  run_ui.bat --demo  shows example lines instead of connecting to VRChat
start "" "%PY%" -m ui.main %*
