@echo off
cd /d "%~dp0"
set PYTHONUTF8=1

where pythonw.exe >nul 2>nul

if errorlevel 1 (
    start "" python "%~dp0run_gui.py"
) else (
    start "" pythonw.exe "%~dp0run_gui.pyw"
)

exit /b
