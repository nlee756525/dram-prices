# DRAM Price Dashboard — Project Reference

**Live dashboard:** https://nlee756525.github.io/dram-prices/
**Repo:** https://github.com/nlee756525/dram-prices
**Manual update form:** https://nlee756525.github.io/dram-prices/update.html

---

## What This Project Does

Tracks two spot price rows from https://www.dramexchange.com/ and displays them
on a GitHub Pages dashboard:

- **DDR5 16Gb (2Gx8) 4800/5600** — from the "DRAM Spot Price" table (updates daily, weekdays)
- **512Gb TLC** — from the "Wafer Spot Price" table (updates weekly, typically Mondays)

Fields captured per row: Weekly High, Weekly Low, Session High, Session Low,
Session Average, Average Change (%).

---

## Architecture

```
history.json        ← single source of truth; all price data lives here
index.html          ← dynamic dashboard; fetches history.json via JS at load time
update.html         ← manual data-entry form; pushes to history.json via GitHub API
scrape.py           ← Playwright scraper; runs via GitHub Actions; only updates history.json
.github/workflows/
  scrape.yml        ← runs scrape.py at 6:30 AM ET every weekday
```

### How index.html works
`index.html` is a static file served by GitHub Pages. It fetches `history.json`
at runtime using JavaScript. The latest entry for each product appears as large
cards at the top; the full price history is in tables below (newest first).
**You never need to regenerate or edit index.html** — updating history.json is enough.

### Why index.html is dynamic (not generated)
Previously scrape.py regenerated index.html on every run. This was changed so
that only history.json needs to be updated, making both manual and automated
updates simpler.

---

## Automated Updates (GitHub Actions)

**File:** `.github/workflows/scrape.yml`
**Schedule:** 6:30 AM ET (10:30 UTC), Monday–Friday
**Manual trigger:** GitHub → Actions tab → "Scrape DRAM Prices" → Run workflow

The workflow:
1. Spins up a GitHub-hosted Ubuntu VM (your computer does NOT need to be on)
2. Installs Python + Playwright + Chromium
3. Runs `scrape.py`
4. Saves a debug screenshot (`scrape-debug.png`) as an Actions artifact (14-day retention)

### Why 6:30 AM ET
DRAMeXchange posts its daily DRAM update at approximately 18:10 GMT+8 = 6:10 AM ET.
The workflow fires 20 minutes later, before the user's normal morning routine.
Running earlier than 6:10 AM ET would capture stale (previous day's) data.

### Why Playwright (real browser)
DRAMeXchange returns HTTP 403 to all plain HTTP clients (curl, requests, WebFetch).
Playwright launches a full headless Chromium browser, which the site allows.

### How scrape.py decides what to record
- **DDR5:** Added for today's date if no entry already exists for today.
- **TLC:** Added only when ≥6 days have passed since the last TLC entry (weekly cadence).
- If DDR5 already exists for today, the script exits early with success (no duplicate).

---

## Manual Data Entry

Use **https://nlee756525.github.io/dram-prices/update.html** when you need to
add data yourself (e.g., if the automated run failed or you are correcting values).

1. Enter your GitHub token once — it is saved in the browser's localStorage
2. The date pre-fills to today
3. Fill in the 6 DDR5 values from DRAMeXchange
4. Tick the TLC checkbox only on weeks when TLC shows a new price
5. Click "Push to GitHub" — history.json updates and the dashboard reflects it within ~30 seconds

**GitHub token:** stored in browser localStorage under key `__dram_gh_token`
Token needs `repo` scope on the `nlee756525/dram-prices` repository.

---

## history.json Format

```json
{
  "ddr5": [
    {
      "date": "6/1/2026",
      "weekly_high": "$53.000",
      "weekly_low": "$30.500",
      "session_high": "$53.000",
      "session_low": "$30.500",
      "session_avg": "$42.267",
      "session_change": "+0.88%"
    }
  ],
  "tlc": [
    {
      "date": "5/25/2026",
      "weekly_high": "$22.000",
      "weekly_low": "$16.000",
      "session_high": "$22.000",
      "session_low": "$16.000",
      "session_avg": "$20.638",
      "session_change": "-0.33%"
    }
  ]
}
```

- Date format: `M/D/YYYY` (no leading zeros) — must be consistent
- Prices: `$XX.XXX` (3 decimal places)
- Change: `+X.XX%`, `-X.XX%`, or `0.00%`
- Entries are in **chronological order** (oldest first); index.html reverses them for display

---

## Key Files

| File | Purpose |
|---|---|
| `history.json` | All price data — the only file that needs updating |
| `index.html` | Dashboard — do not edit; loads data from history.json dynamically |
| `update.html` | Browser-based manual entry form |
| `scrape.py` | Playwright scraper — reads GITHUB_TOKEN env var, updates history.json via API |
| `.github/workflows/scrape.yml` | GitHub Actions workflow — schedule + steps |
| `bookmarklet.html` | Old approach (bookmarklet run on DRAMeXchange in browser) — superseded |
| `config.json.example` | Example config for running scrape.py locally with a config file |

---

## Troubleshooting

| Problem | What to check |
|---|---|
| Dashboard date not advancing | GitHub Actions tab — check if the 6:30 AM run ✅ or ❌ |
| Workflow shows ✅ but no new data | The scraper found today's date already in history.json (duplicate) — was data added manually before 6:30 AM? |
| Workflow shows ❌ | Download the `scrape-debug-XXXXX` artifact from the failed run — the screenshot shows exactly what Playwright saw (blocked page vs real data) |
| DRAMeXchange blocked Playwright | The screenshot will show a Cloudflare/403 page — come back to Claude and request stealth mode (`playwright-extra` + stealth plugin) |
| Wrong values scraped | Check the screenshot; DRAMeXchange may have changed their table layout — update the `filter(has_text=...)` selectors in scrape.py |
| TLC not updating | Expected — TLC only records when ≥6 days have passed since the last entry |
| Need to correct a bad entry | Use update.html won't help for edits — ask Claude to directly patch history.json via the GitHub API |

---

## History of Changes (as of June 2026)

- **May 2026:** Project created; scrape.py + GitHub Actions workflow set up
- **June 1, 2026 session with Claude:**
  - `index.html` redesigned to be dynamic (fetches history.json via JS) — no more HTML regeneration
  - `update.html` created as a manual entry form (browser-based, uses GitHub API)
  - `scrape.py` updated to only push `history.json` (removed HTML regeneration)
  - Workflow schedule changed from **8:45 AM ET → 6:30 AM ET** so it runs before the user's morning routine
  - Debug screenshot artifact added to workflow for diagnosing failures
  - Root cause identified: workflow was always a no-op because user was adding data before 8:45 AM; fix was the schedule change

---

## Key Context for Claude Sessions

- DRAMeXchange **always returns 403** to plain HTTP requests (curl, WebFetch, requests). Never try to fetch it directly — only Playwright works.
- The dashboard URL is the GitHub Pages URL. The raw repo is at github.com/nlee756525/dram-prices.
- All historical data is in `history.json` — fetch it with `curl -s "https://raw.githubusercontent.com/nlee756525/dram-prices/main/history.json"` to see current state.
- To push file changes, use the GitHub Contents API (PUT to `https://api.github.com/repos/nlee756525/dram-prices/contents/<file>`) with the file's current SHA.
- The GitHub token in use is stored in the user's browser localStorage and should not be hardcoded in any public file.
- DDR5 updates every **weekday**; TLC updates every **Monday** (weekly).
- The user manually copies numbers from DRAMeXchange and either pastes them into this chat or uses update.html. The automation is meant to eliminate this entirely.
