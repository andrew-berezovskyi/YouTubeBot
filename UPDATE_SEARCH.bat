@echo off
cd /d "%~dp0"
python -m pip install --upgrade "yt-dlp[default]"
if errorlevel 1 goto failed
python apply_search_update.py
if errorlevel 1 goto failed
python check_discovery.py
if errorlevel 1 goto failed
echo Update completed. Start START_DISCOVERY.bat
pause
exit /b 0
:failed
echo Update or dependency check failed. Read the message above.
echo If Deno is missing: winget install --id DenoLand.Deno -e
 echo Then restart VS Code and run this file again.
pause
exit /b 1
