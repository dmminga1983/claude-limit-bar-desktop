@echo off
rem Claude Limit Bar - installer for Windows.
rem Messages are ASCII on purpose: cmd.exe mangles non-ASCII text in .bat files.
setlocal
cd /d "%~dp0"
set "LOG=install_log.txt"
echo === Claude Limit Bar install === > "%LOG%"
echo Started: %date% %time% >> "%LOG%"

rem --- 1. Find a REAL Python 3.9+ (the Microsoft Store "python.exe" stub does not count) ---
set "PY="
for %%C in ("py -3" "python") do (
    if not defined PY (
        %%~C -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
        if not errorlevel 1 set "PY=%%~C"
    )
)
rem Per-user Python 3.12 (as installed by setup_python.bat) may not be on PATH yet in this session.
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" -c "import sys" >nul 2>nul
    if not errorlevel 1 set PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
if not defined PY (
    echo RESULT: PYTHON_MISSING >> "%LOG%"
    echo No working Python 3.9+ found. If "where python" points to WindowsApps, that is only >> "%LOG%"
    echo the Microsoft Store stub, not a real Python. >> "%LOG%"
    echo Install Python 3.12 from https://www.python.org/downloads/ and tick "Add python.exe to PATH", >> "%LOG%"
    echo then run install.bat again. >> "%LOG%"
    goto :fail
)
echo Using: %PY% >> "%LOG%"
%PY% --version >> "%LOG%" 2>&1

rem --- 2. Virtual environment ---
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment... >> "%LOG%"
    %PY% -m venv .venv >> "%LOG%" 2>&1
)
if not exist ".venv\Scripts\python.exe" (
    echo RESULT: VENV_FAILED >> "%LOG%"
    goto :fail
)

rem --- 3. Dependencies ---
echo Installing dependencies... >> "%LOG%"
".venv\Scripts\python.exe" -m pip install --upgrade pip >> "%LOG%" 2>&1
".venv\Scripts\python.exe" -m pip install -r requirements.txt >> "%LOG%" 2>&1
if errorlevel 1 (
    echo RESULT: PIP_FAILED >> "%LOG%"
    echo Tip: Python 3.12 is the safest choice; very new Python versions may lack wheels for pywebview/pythonnet. >> "%LOG%"
    goto :fail
)

rem --- 4. Tests (do not block the install if they fail, just record) ---
".venv\Scripts\python.exe" -m pip install pytest >> "%LOG%" 2>&1
".venv\Scripts\python.exe" -m pytest -q >> "%LOG%" 2>&1
if errorlevel 1 (echo TESTS: FAILED >> "%LOG%") else (echo TESTS: OK >> "%LOG%")

rem --- 5. Autostart shortcut ---
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "VBS=%TEMP%\clb_shortcut.vbs"
> "%VBS%" echo Set s = CreateObject("WScript.Shell").CreateShortcut("%STARTUP%\ClaudeLimitBar.lnk")
>> "%VBS%" echo s.TargetPath = "%~dp0.venv\Scripts\pythonw.exe"
>> "%VBS%" echo s.Arguments = "-m app.main"
>> "%VBS%" echo s.WorkingDirectory = "%~dp0"
>> "%VBS%" echo s.Description = "Claude Limit Bar"
>> "%VBS%" echo s.Save
cscript //nologo "%VBS%" >> "%LOG%" 2>&1
del "%VBS%" >nul 2>nul

rem --- 6. Launch ---
echo Launching... >> "%LOG%"
start "" ".venv\Scripts\pythonw.exe" -m app.main
echo RESULT: INSTALL_OK >> "%LOG%"
echo A sign-in window for claude.ai opens on first start; afterwards the tray icon appears. >> "%LOG%"
goto :eof

:fail
echo See %LOG% for details.
notepad "%LOG%"
exit /b 1
