@echo off
:: Starts a local web server so you can access dram_prices.html via browser URL.
:: Keep this window open while you want the site to be accessible.

set PORT=8080
set SCRIPT_DIR=%~dp0

echo.
echo ============================================================
echo  DRAM Price Dashboard — Local Web Server
echo  URL: http://localhost:%PORT%/dram_prices.html
echo  Keep this window open. Press Ctrl+C to stop.
echo ============================================================
echo.

cd /d "%SCRIPT_DIR%"
start "" "http://localhost:%PORT%/dram_prices.html"
python -m http.server %PORT%
