@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0open_local.ps1"
if errorlevel 1 (
    echo.
    echo NeighLoop could not open. Read the error above, then press any key to close.
    pause >nul
    exit /b 1
)
exit /b 0
