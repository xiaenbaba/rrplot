@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Project Python environment was not found.
  echo See web\README.md for setup instructions.
  pause
  exit /b 1
)
echo Open http://127.0.0.1:8765 in your browser.
echo Keep this window open while using the editor. Press Ctrl+C to stop.
".venv\Scripts\python.exe" "server\run.py" %*
if errorlevel 1 pause
