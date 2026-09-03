@echo off
setlocal
cd /d "%~dp0"
if not exist "runtime\venv\Scripts\python.exe" (
    echo SPIDER: Project-local Python runtime is missing.
    pause
    exit /b 1
)
"runtime\venv\Scripts\python.exe" -m spider.launcher start %*
if errorlevel 1 (
    pause
    exit /b 1
)
