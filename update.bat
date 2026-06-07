@echo off
echo Warte auf Server-Shutdown...
timeout /t 3 /nobreak >nul
taskkill /F /PID %1 >nul 2>&1
cd /d "%~dp0"
echo Update wird heruntergeladen...
git pull
echo Starte Server neu...
call .venv\Scripts\activate.bat
python app.py
