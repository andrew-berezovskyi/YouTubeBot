@echo off
cd /d "%~dp0"
python recheck_detector.py
if errorlevel 1 echo Recheck preparation failed. Read the error above.
pause
