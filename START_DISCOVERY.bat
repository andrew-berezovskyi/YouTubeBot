@echo off
cd /d "%~dp0"
python run_discovery_gui.py
if errorlevel 1 pause
