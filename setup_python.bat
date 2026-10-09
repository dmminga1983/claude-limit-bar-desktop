@echo off
rem Downloads the official Python 3.12 installer from python.org, verifies its signature,
rem installs it for the current user only (no admin rights), then runs install.bat.
setlocal
cd /d "%~dp0"
set "LOG=setup_log.txt"
set "PYVER=3.12.10"
set "EXE=%TEMP%\python-%PYVER%-amd64.exe"
echo === Python setup === > "%LOG%"
echo Started: %date% %time% >> "%LOG%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-amd64.exe' -OutFile '%EXE%'" >> "%LOG%" 2>&1
if not exist "%EXE%" (
    echo RESULT: DOWNLOAD_FAILED >> "%LOG%"
    goto :fail
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=Get-AuthenticodeSignature '%EXE%'; if($s.Status -eq 'Valid' -and $s.SignerCertificate.Subject -like '*Python Software Foundation*'){exit 0}else{Write-Output ('Bad signature: '+$s.Status); exit 1}" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo RESULT: SIGNATURE_INVALID >> "%LOG%"
    del "%EXE%" >nul 2>nul
    goto :fail
)
echo Signature OK >> "%LOG%"

"%EXE%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0 Include_doc=0 Shortcuts=0 >> "%LOG%" 2>&1
set "RC=%errorlevel%"
echo Installer exit code: %RC% >> "%LOG%"
del "%EXE%" >nul 2>nul
if not exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    echo RESULT: PYTHON_INSTALL_FAILED >> "%LOG%"
    goto :fail
)
echo RESULT: PYTHON_OK >> "%LOG%"
call "%~dp0install.bat"
goto :eof

:fail
echo See %LOG% for details.
notepad "%LOG%"
exit /b 1
