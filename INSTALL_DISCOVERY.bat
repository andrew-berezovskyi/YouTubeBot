@echo off
cd /d "%~dp0"
if not exist config.py copy /Y config.example.py config.py
python -m pip install -r requirements.txt
if errorlevel 1 goto :failed
python -m playwright install chromium
if errorlevel 1 goto :failed
echo Python dependencies installed. See START_HERE_UK.md for FFmpeg, Ollama and Tesseract.
pause
exit /b 0
:failed
echo Installation failed. Read the error above.
pause
exit /b 1
