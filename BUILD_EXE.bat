@echo off
setlocal
cd /d "%~dp0"

echo ========================================================
echo              VIBERUSH YOUTUBE BOT - BUILD
echo ========================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python was not found in PATH.
    pause
    exit /b 1
)

echo [1/4] Installing/updating PyInstaller...
python -m pip install --upgrade pyinstaller pyinstaller-hooks-contrib
if errorlevel 1 goto :error

echo.
echo [2/4] Cleaning old build folders...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo [3/4] Building GUI + hidden backend...
python -m PyInstaller --noconfirm --clean YouTubeBot.spec
if errorlevel 1 goto :error

echo.
echo [4/4] Copying EXEs to project root...
copy /y "dist\VibeRush YouTube Bot.exe" "%~dp0VibeRush YouTube Bot.exe" >nul
if errorlevel 1 goto :error

copy /y "dist\_VibeRushBackend.exe" "%~dp0_VibeRushBackend.exe" >nul
if errorlevel 1 goto :error

echo.
echo ========================================================
echo BUILD COMPLETED
echo ========================================================
echo.
echo Run:
echo   VibeRush YouTube Bot.exe
echo.
echo Keep this helper next to it:
echo   _VibeRushBackend.exe
echo.
echo The app will reuse the existing local folders:
echo   BrowserProfile
echo   data
echo   ToUpload
echo   Uploaded
echo   Watermark
echo   Logs
echo.
pause
exit /b 0

:error
echo.
echo ========================================================
echo BUILD FAILED
echo ========================================================
echo.
echo Scroll up and send the error output.
echo.
pause
exit /b 1
