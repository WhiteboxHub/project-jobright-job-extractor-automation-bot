@echo off
setlocal

:: ============================================================
:: jobright_scheduler_launcher.bat
:: ============================================================

set "ROOT=C:\Users\Innovapath\Desktop\job_engine\jobright-engine"
set "VENV=%ROOT%\venv\Scripts\python.exe"
set "SCRIPT=%ROOT%\jobright_scheduler.py"

:: UTF-8 console for Unicode logging
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set SCHEDULER_LAUNCHED=1

if not exist "%VENV%" (
    echo [%date% %time%] ERROR: venv not found at %VENV%
    pause
    exit /b 1
)

if not exist "%ROOT%\.env" (
    echo [%date% %time%] ERROR: .env file not found in %ROOT%
    pause
    exit /b 1
)

if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"

:: ── Log file paths ────────────────────────────────────────────────────────────
set "BASE_LOG=%ROOT%\logs\scheduler_bat_rolling.log"
set "FULL_LOG=%ROOT%\logs\scheduler_bat.log"

:: Clear the rolling log at the START of each run
echo. > "%BASE_LOG%"

echo [%date% %time%] Starting Jobright Scheduler (Launcher)... >> "%BASE_LOG%"
echo Starting Jobright Scheduler (Launcher)...

:: ── Run Python with --force if needed, currently running normally ─────────────
"%VENV%" "%SCRIPT%" --force >> "%BASE_LOG%" 2>&1
set EXIT_CODE=%errorlevel%

echo [%date% %time%] Scheduler finished with exit code %EXIT_CODE% >> "%BASE_LOG%"
echo Scheduler finished with exit code %EXIT_CODE%

:: Append this run's log to the full historical log
type "%BASE_LOG%" >> "%FULL_LOG%" 2>nul

timeout /t 10
endlocal
