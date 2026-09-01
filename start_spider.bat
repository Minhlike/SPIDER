@echo off
setlocal enabledelayedexpansion

echo =================================================================
echo        SPIDER — Evidence-First OSINT Orchestration Engine        
echo =================================================================

set "ROOT=%~dp0"
set "PYTHON=%ROOT%runtime\venv\Scripts\python.exe"
set "PORT=8765"
set "HOST=127.0.0.1"
set "PID_FILE=%ROOT%data\spider.pid"

if not exist "%PYTHON%" (
    echo [ERROR] Virtual environment not found at %PYTHON%
    pause
    exit /b 1
)

:: Check if already running
if exist "%PID_FILE%" (
    set /p OLD_PID=<"%PID_FILE%"
    tasklist /FI "PID eq !OLD_PID!" 2>NUL | find /I "!OLD_PID!" >NUL
    if not errorlevel 1 (
        echo [INFO] SPIDER backend is already running on PID !OLD_PID!.
        echo Opening browser at http://%HOST%:%PORT% ...
        start http://%HOST%:%PORT%
        exit /b 0
    )
)

echo [INFO] Starting SPIDER backend on http://%HOST%:%PORT% ...

:: Launch background uvicorn server via PowerShell start-process to capture PID reliably
powershell -NoProfile -Command ^
    "$proc = Start-Process -FilePath '%PYTHON%' -ArgumentList '-m uvicorn spider.web.app:create_app --factory --host %HOST% --port %PORT%' -WorkingDirectory '%ROOT%' -PassThru -WindowStyle Hidden; Set-Content -Path '%PID_FILE%' -Value $proc.Id"

echo [INFO] Waiting for SPIDER health endpoint to become ready...
set /a ATTEMPTS=0

:WAIT_LOOP
timeout /t 1 /nobreak >NUL
set /a ATTEMPTS+=1

powershell -NoProfile -Command ^
    "try { $r = Invoke-WebRequest -Uri 'http://%HOST%:%PORT%/api/health' -TimeoutSec 2 -UseBasicParsing; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >NUL 2>&1

if %errorlevel% equ 0 (
    echo [SUCCESS] SPIDER backend is online!
    echo [INFO] Opening default browser at http://%HOST%:%PORT% ...
    start http://%HOST%:%PORT%
    echo =================================================================
    echo SPIDER is active. Use stop_spider.bat to gracefully terminate.
    echo =================================================================
    exit /b 0
)

if %ATTEMPTS% geq 20 (
    echo [ERROR] Timed out waiting for SPIDER backend to initialize.
    echo Check logs in %ROOT%logs\
    pause
    exit /b 1
)

goto WAIT_LOOP