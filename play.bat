@echo off
rem Same entrypoint on Windows as play.sh is for macOS/Linux: finds (or
rem installs) a system Python 3, then hands off to play.py, which does
rem everything else (venv + dependency install, build-toolchain check,
rem building melonDS if needed, launching, QR codes, the web server).
rem See play.py for the actual logic.
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "PYEXE=python"
    goto :run
)

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "PYEXE=py"
    goto :run
)

echo [ERROR] No Python 3 found.
where winget >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [INFO] Installing Python 3 via winget...
    winget install -e --id Python.Python.3.12
    echo [INFO] Installed. Close this window and re-run play.bat so PATH picks it up.
    exit /b 1
) else (
    echo         Install Python 3 from https://python.org/downloads/ then re-run.
    exit /b 1
)

:run
"%PYEXE%" play.py %*
