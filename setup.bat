@echo off
setlocal EnableDelayedExpansion

:: ── DRAMeXchange Scraper — One-click setup for Windows ───────────────────────
:: Run once as Administrator. It will:
::   1. Install Python dependencies (Playwright)
::   2. Download Chromium to C:\PlaywrightBrowsers  (shared, accessible to SYSTEM)
::   3. Register a daily Task Scheduler job that runs whether you are logged in or not
::      and can wake the PC from sleep to run

set SCRIPT_DIR=%~dp0
set SCRIPT=%SCRIPT_DIR%scrape.py
set WRAPPER=%SCRIPT_DIR%run_scraper.bat
set TASK_NAME=DRAMeXchange Scraper
set RUN_TIME=08:45
set BROWSERS_PATH=C:\PlaywrightBrowsers

echo.
echo ============================================================
echo  DRAMeXchange Scraper — Setup  (run as Administrator)
echo ============================================================
echo.

:: ── 1. Check Python ──────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.8+ from https://python.org
    pause & exit /b 1
)
for /f "delims=" %%i in ('where python') do set PYTHON_EXE=%%i
echo [OK] Python: %PYTHON_EXE%

:: ── 2. Install Playwright ────────────────────────────────────────────────────
echo.
echo [1/3] Installing Playwright...
pip install playwright
if errorlevel 1 ( echo [ERROR] pip install failed. & pause & exit /b 1 )

:: ── 3. Download Chromium to shared location ──────────────────────────────────
echo.
echo [2/3] Downloading Chromium to %BROWSERS_PATH% (one-time, ~200 MB)...
set PLAYWRIGHT_BROWSERS_PATH=%BROWSERS_PATH%
python -m playwright install chromium
if errorlevel 1 ( echo [ERROR] Playwright browser install failed. & pause & exit /b 1 )
echo [OK] Chromium installed at %BROWSERS_PATH%

:: ── 4. Register Task Scheduler job via PowerShell ────────────────────────────
echo.
echo [3/3] Registering Task Scheduler job "%TASK_NAME%"...
echo       Runs at %RUN_TIME% daily, as SYSTEM (no login needed), wakes from sleep.

powershell -NoProfile -ExecutionPolicy Bypass -Command " ^
    $action   = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument ('/c \"%WRAPPER%\"'); ^
    $trigger  = New-ScheduledTaskTrigger -Daily -At '%RUN_TIME%'; ^
    $settings = New-ScheduledTaskSettingsSet ^
                    -WakeToRun ^
                    -RunOnlyIfNetworkAvailable ^
                    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) ^
                    -MultipleInstances IgnoreNew ^
                    -DisallowStartIfOnBatteries:$false ^
                    -StopIfGoingOnBatteries:$false; ^
    $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest; ^
    Register-ScheduledTask -TaskName '%TASK_NAME%' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null; ^
    Write-Host '[OK] Task registered.' ^
"

if errorlevel 1 (
    echo [WARN] Task registration failed. Make sure you ran this as Administrator.
    echo        Right-click setup.bat ^> Run as administrator, then try again.
) else (
    echo [OK] Task "%TASK_NAME%" scheduled daily at %RUN_TIME%.
    echo      Runs as SYSTEM - no login required.
    echo      Wakes PC from sleep if needed.
    echo      NOTE: PC must be ON or SLEEPING (not shut down) to run automatically.
    echo      Recommended: set Windows power plan to Sleep instead of Shut Down.
)

:: ── 5. Run scraper now ────────────────────────────────────────────────────────
echo.
echo Running scraper now for the first time...
set PLAYWRIGHT_BROWSERS_PATH=%BROWSERS_PATH%
python "%SCRIPT%"

echo.
echo ============================================================
echo  Setup complete!
echo  - Log file  : %SCRIPT_DIR%scraper.log
echo  - Runs daily: %RUN_TIME% (Task Scheduler, no login needed)
echo.
echo  ALSO RECOMMENDED: Enable the GitHub Actions workflow for
echo  fully cloud-based scraping (no PC required at all).
echo  See .github/workflows/scrape.yml in your repo.
echo ============================================================
echo.
pause
