@echo off
rem Calorie Tracker - Windows launcher. Works from any folder: switches to the folder of this file.
cd /d "%~dp0"
echo Starting Calorie Tracker backend on port 8787...
echo Open http://127.0.0.1:8787 in your browser. Close this window to stop.
python -m backend serve --port 8787
pause
