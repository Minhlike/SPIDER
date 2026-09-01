@echo off
setlocal enabledelayedexpansion

echo =================================================================
echo                    Stopping SPIDER Backend                       
echo =================================================================

set "ROOT=%~dp0"
set "PID_FILE=%ROOT%data\spider.pid"

if not exist "%PID_FILE%" (
    echo [INFO] No active spider.pid file found. SPIDER does not appear to be running.
    exit /b 0
)

set /p SPIDER_PID=<"%PID_FILE%"

if "%SPIDER_PID%"=="" (
    echo [INFO] PID file is empty.
    del "%PID_FILE%" 2>NUL
    exit /b 0
)

echo [INFO] Terminating SPIDER backend process PID: %SPIDER_PID% ...
taskkill /PID %SPIDER_PID% /T /F >NUL 2>&1

if %errorlevel% equ 0 (
    echo [SUCCESS] SPIDER backend (PID %SPIDER_PID%) terminated cleanly.
) else (
    echo [INFO] Process PID %SPIDER_PID% was not running.
)

del "%PID_FILE%" 2>NUL
echo [INFO] Cleaned up PID file.