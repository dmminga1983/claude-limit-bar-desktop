@echo off
rem Runs Claude Limit Bar through the console python.exe (not pythonw.exe), so any
rem crash or Python traceback lands in debug_log.txt instead of being silently
rem swallowed by the windowless pythonw.exe process. Use this if install.bat
rem finished with RESULT: INSTALL_OK but no tray icon / window ever shows up.
setlocal
cd /d "%~dp0"
taskkill /F /IM pythonw.exe >nul 2>nul
echo killed old pythonw (if any) > debug_log.txt
echo Starting at %date% %time% >> debug_log.txt
start "" /B ".venv\Scripts\python.exe" -u -m app.main >> debug_log.txt 2>&1
echo Launched, PID check: >> debug_log.txt
tasklist /FI "IMAGENAME eq python.exe" >> debug_log.txt
echo DONE_LAUNCH >> debug_log.txt
notepad debug_log.txt
