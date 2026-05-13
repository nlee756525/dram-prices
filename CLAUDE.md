# DRAM Price Dashboard — Project Instructions

This document is the complete reference for reproducing, maintaining, and extending
this project. Follow every step in order when setting up from scratch.

---

## What This Project Does

Scrapes two spot price rows from https://www.dramexchange.com/ every day at 08:45 AM:

- **DDR5 16Gb (2Gx8) 4800/5600** — from the "DRAM Spot Price" table
- **512Gb TLC** — from the "Wafer Spot Price" table

Fields captured per row: Daily/Weekly High, Daily/Weekly Low, Session High,
Session Low, Session Average, Session Change (%).

Data is appended to `history.json`, rendered into `index.html`, and pushed
automatically to GitHub Pages so the live URL updates within ~30 seconds.

**Live URL:** https://nlee756525.github.io/dram-prices/
**GitHub repo:** https://github.com/nlee756525/dram-prices

---

## File Structure

```
dram_scraper/
├── scrape.py          Main script — scrapes, builds HTML, pushes to GitHub
├── setup.bat          Run once on Windows to install deps + schedule daily task
├── start_server.bat   Optional local server at http://localhost:8080/index.html
├── config.env         GitHub credentials — NEVER commit this file
├── .gitignore         Excludes config.env, scraper.log, __pycache__
├── history.json       Accumulates all scraped rows by date
├── index.html         Generated dashboard served by GitHub Pages
└── scraper.log        Appended on every run; check here if scrape fails
```

---

## One-Time Setup (Windows)

### Prerequisites
- Python 3.8+ installed and on PATH
- Git installed (https://git-scm.com/download/win)
- A GitHub account

### Step 1 — Copy files to Windows
Place the entire `dram_scraper/` folder anywhere on the PC, e.g.:
```
C:\Users\<you>\dram_scraper\
```

### Step 2 — Create config.env
Create `dram_scraper\config.env` with the following content (fill in real values):
```
GITHUB_TOKEN=<personal access token with repo scope>
GITHUB_USER=<github username>
GITHUB_REPO=dram-prices
```
This file must NOT be committed to GitHub. It is already listed in `.gitignore`.

To create a GitHub Personal Access Token:
1. GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Generate new token (classic)
3. Check the `repo` scope only
4. Copy the token into `config.env`

### Step 3 — Create the GitHub repository
Run this once in PowerShell or Command Prompt (replace values):
```
curl -s -X POST ^
  -H "Authorization: token <GITHUB_TOKEN>" ^
  -H "Accept: application/vnd.github.v3+json" ^
  https://api.github.com/user/repos ^
  -d "{\"name\":\"dram-prices\",\"private\":false,\"auto_init\":false}"
```

### Step 4 — Enable GitHub Pages on the repo
Run this once:
```
curl -s -X POST ^
  -H "Authorization: token <GITHUB_TOKEN>" ^
  -H "Accept: application/vnd.github.v3+json" ^
  https://api.github.com/repos/<GITHUB_USER>/dram-prices/pages ^
  -d "{\"source\":{\"branch\":\"main\",\"path\":\"/\"}}"
```

### Step 5 — Run setup.bat
Double-click `setup.bat` (or right-click → Run as administrator if scheduler fails).

What it does:
1. Installs Playwright: `pip install playwright`
2. Downloads Chromium: `python -m playwright install chromium`
3. Configures git remote using credentials from `config.env`
4. Registers a Windows Task Scheduler job named "DRAMeXchange Scraper" to run
   `scrape.py` daily at 08:45 AM
5. Runs `scrape.py` immediately for the first time

---

## How scrape.py Works

1. Launches headless Chromium via Playwright
2. Navigates to https://www.dramexchange.com/
3. Waits for `text=DRAM Spot Price` to appear (confirms tables are loaded)
4. Waits an additional 2 seconds for dynamic data to finish rendering
5. Finds the row containing "4800/5600" → extracts 6 cell values
6. Finds the row containing "512Gb TLC" → extracts 6 cell values
7. Loads `history.json`; appends today's entry if the date is not already present
8. Saves updated `history.json`
9. Renders `index.html` from the full history (newest row first)
10. Calls the GitHub Contents API to PUT `index.html` and `history.json`
    into the `nlee756525/dram-prices` repo on branch `main`
11. GitHub Pages publishes the update within ~30 seconds

### Why Playwright instead of requests/curl
DRAMeXchange returns HTTP 403 to all server-side HTTP clients. Playwright
launches a real Chromium browser which the site cannot distinguish from a
normal user visit.

### GitHub push (no git required)
`scrape.py` uses Python's built-in `urllib` to call the GitHub Contents API
directly. It does not run any `git` commands at scrape time. The `setup.bat`
configures git only once (for the initial push of the repo files).

---

## Daily Workflow (Automatic)

```
08:45 AM  Task Scheduler fires
          → python scrape.py
          → Chromium loads dramexchange.com
          → Rows extracted, history.json updated
          → index.html regenerated
          → GitHub API updates both files
          → https://nlee756525.github.io/dram-prices/ reflects new data
```

No manual action needed once setup is complete.

---

## Viewing the Dashboard

Open in any browser:
```
https://nlee756525.github.io/dram-prices/
```

Or locally (without internet):
```
Double-click index.html
```

Or via local server:
```
Double-click start_server.bat  →  http://localhost:8080/index.html
```

---

## Troubleshooting

| Symptom | Check |
|---|---|
| Page not updating | `scraper.log` — look for errors on the last run |
| GitHub push fails | Token may have expired — generate a new one, update `config.env` |
| Scrape returns N/A | DRAMeXchange may have changed their table layout — inspect the page and update the `filter(has_text=...)` selectors in `scrape.py` |
| Task Scheduler not firing | Open Task Scheduler, find "DRAMeXchange Scraper", check Last Run Result |
| Chromium download fails | Run `python -m playwright install chromium` manually in the `dram_scraper` folder |

---

## Changing the Schedule

Open `setup.bat`, change:
```
set RUN_TIME=08:45
```
to any HH:MM time, then re-run `setup.bat`.

Or edit the task directly in Windows Task Scheduler.

---

## Re-creating from Scratch

If the repo or files are lost, repeat Steps 1–5 above.
The historical data lives in `history.json` — back this file up to preserve
the full price history. If it is lost, the next scrape will start a fresh history.

---

## Key Values

| Item | Value |
|---|---|
| GitHub user | nlee756525 |
| GitHub repo | dram-prices |
| GitHub Pages URL | https://nlee756525.github.io/dram-prices/ |
| Scrape time | 08:45 AM daily |
| Target product 1 | DDR5 16Gb (2Gx8) 4800/5600 (DRAM Spot Price table) |
| Target product 2 | 512Gb TLC (Wafer Spot Price table) |
| Token scope needed | repo |
| Credentials file | config.env (local only, never committed) |
