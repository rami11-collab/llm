@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First complete the setup commands in README.txt.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\start_models.py
if errorlevel 1 (
  pause
  exit /b 1
)
echo Open http://127.0.0.1:8010 in your browser.
".venv\Scripts\python.exe" app.py
".venv\Scripts\python.exe" scripts\stop_models.py
