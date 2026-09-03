@echo off
setlocal
cd /d "%~dp0"
"runtime\venv\Scripts\python.exe" -m spider.launcher stop
if errorlevel 1 (
    pause
    exit /b 1
)
