@echo off
cd /d "%~dp0"

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "VibeRush YouTube Bot.exe" del /q "VibeRush YouTube Bot.exe"
if exist "_VibeRushBackend.exe" del /q "_VibeRushBackend.exe"

echo Build files cleaned.
pause
