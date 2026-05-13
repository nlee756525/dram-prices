@echo off
setlocal

:: ── DRAMeXchange Scraper — One-click setup for Windows ───────────────────────
:: Run this once. It will:
::   1. Install Python dependencies (Playwright)
::   2. Download the Chromium browser used for scraping
::   3. Register a daily Task Scheduler job at 18:30

set SCRIPT_DIR=%~dp0
set SCRIPT=%SCRIPT_DIR%scrape.py
set TASK_NAME=DRAMeXchange Scraper
set RUN_TIME=08:45

echo.
echo ============================================================
echo  DRAMeXchange Scraper — Setup
echo ============================================================
echo.

:: ── 1. Check Python ──────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.8+ from https://python.org
    pause
    exit /b 1
)

:: ── 2. Install Playwright ────────────────────────────────────────────────────
echo [1/3] Installing Playwright...
pip install playwright
if errorlevel 1 (
    echo [ERROR] pip install failed. Make sure pip is available.
    pause
    exit /b 1
)

:: ── 3. Download Chromium ─────────────────────────────────────────────────────
echo.
echo [2/3] Downloading Chromium browser (one-time, ~200 MB)...
python -m playwright install chromium
if errorlevel 1 (
    echo [ERROR] Playwright browser install failed.
    pause
    exit /b 1
)

:: ── 4. Register daily Task Scheduler job ────────────────────────────────────
echo.
echo [3/3] Registering daily Task Scheduler job at %RUN_TIME%...

:: Find the full path to python.exe
for /f "delims=" %%i in ('where python') do set PYTHON_EXE=%%i

schtasks /create ^
  /tn "%TASK_NAME%" ^
  /tr "\"%PYTHON_EXE%\" \"%SCRIPT%\"" ^
  /sc daily ^
  /st %RUN_TIME% ^
  /f ^
  /rl highest

if errorlevel 1 (
    echo [WARN] Task Scheduler registration failed. You may need to run this as Administrator.
    echo        To retry, right-click setup.bat and choose "Run as administrator".
) else (
    echo [OK] Task "%TASK_NAME%" scheduled daily at %RUN_TIME%.
)

:: ── 5. Run scraper immediately ───────────────────────────────────────────────
echo.
echo Running scraper now for the first time...
echo Output: %SCRIPT_DIR%dram_prices.html
echo.
python "%SCRIPT%"

echo.
echo ============================================================
echo  Setup complete!
echo  - Dashboard : %SCRIPT_DIR%dram_prices.html
echo  - Log file  : %SCRIPT_DIR%scraper.log
echo  - Runs daily: %RUN_TIME% (Task Scheduler)
echo.
echo  To change the run time, edit this file and re-run,
echo  or open Task Scheduler and modify "%TASK_NAME%".
echo ============================================================
echo.
pause
