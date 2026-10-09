@echo off
rem Normal everyday launcher: runs the app via pythonw.exe (no console window
rem at all), fully detached from this .bat file. Closing this window (or the
rem one it briefly flashes) does NOT stop the app - it keeps running in the
rem background with only the tray icon / floating widget visible.
rem Use debug_console.bat instead only when you need to see errors on screen.
setlocal
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" -m app.main
