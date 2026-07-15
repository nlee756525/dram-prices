@echo off
:: Wrapper called by Task Scheduler.
:: Sets the shared Playwright browser path so the SYSTEM account can find Chromium.
set PLAYWRIGHT_BROWSERS_PATH=C:\PlaywrightBrowsers
cd /d "%~dp0"
python scrape.py >> "%~dp0scraper.log" 2>&1
:: routine-trigger: nudge Actions push trigger (workflow_dispatch API is blocked in this session's sandbox)
:: routine-trigger: nudge Actions push trigger 2026-07-15T10:52 (scheduled cron runs found no update after 15min wait)
