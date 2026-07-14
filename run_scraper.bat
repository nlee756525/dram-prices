@echo off
:: Wrapper called by Task Scheduler.
:: Sets the shared Playwright browser path so the SYSTEM account can find Chromium.
set PLAYWRIGHT_BROWSERS_PATH=C:\PlaywrightBrowsers
cd /d "%~dp0"
python scrape.py >> "%~dp0scraper.log" 2>&1
:: routine-trigger: nudge Actions push trigger (workflow_dispatch API is blocked in this session's sandbox)
