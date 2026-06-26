@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Chyba: nebylo nalezeno virtualni prostredi v ".venv".
    echo Nejdrive spust:
    echo   python -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
    exit /b 1
)

set "TRINITY_HOST=127.0.0.1"
set "TRINITY_PORT=5000"
set "TRINITY_THREADS=4"

".venv\Scripts\python.exe" "serve.py"
