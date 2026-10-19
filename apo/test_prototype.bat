@echo off
setlocal
title VRChat Translator - Microphone Mixer Prototype Test
cd /d "%~dp0.."
echo Microphone mixer prototype test
echo.
echo This checks audio internally. You will not hear sound in HyperX or VRChat.
echo No microphone settings will be changed.
echo.
if not exist ".venv-app\Scripts\python.exe" goto missing
if not exist ".tools\apo-prototype-10\ApoTests.exe" goto missing
echo Press any key to start the test.
pause >nul
".venv-app\Scripts\python.exe" "apo\test_python_playback.py" ".tools\apo-prototype-10"
if errorlevel 1 goto failed
echo.
echo PASSED - internal prototype test completed successfully.
goto done
:missing
echo Required local test files are missing. Run this from the development project.
goto done
:failed
echo.
echo FAILED - copy the error above so it can be investigated.
:done
echo.
echo Press any key to close this window.
pause >nul
endlocal
