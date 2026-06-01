#!/usr/bin/env python3
"""
DRAM Price Updater
Scrapes DRAMeXchange with a real browser (Playwright) to avoid 403,
then updates history.json via the GitHub Contents API.

Setup:
    pip install playwright
    playwright install chromium

    Create config.json in the same folder as this script:
    {
      "github_token": "your_token_here",
      "owner": "nlee756525",
      "repo": "dram-prices"
    }

Run manually:
    python scrape.py

Schedule (Mac/Linux cron):
    45 13 * * 1-5 /usr/bin/python3 /path/to/scrape.py >> /path/to/scrape.log 2>&1
"""

import asyncio
import json
import base64
import urllib.request
import urllib.error
import os
from datetime import date, datetime
from pathlib import Path
from playwright.async_api import async_playwright

# ── Config ────────────────────────────────────────────────────────────────────
def load_config():
    config_path = Path(__file__).parent / "config.json"
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError(
            "No GitHub token found.\n"
            "Either create config.json with your token, or set GITHUB_TOKEN env var."
        )
    return {
        "github_token": token,
        "owner": os.environ.get("GITHUB_OWNER", "nlee756525"),
        "repo":  os.environ.get("GITHUB_REPO",  "dram-prices"),
    }

# ── Formatters ────────────────────────────────────────────────────────────────
def today_str():
    d = date.today()
    return f"{d.month}/{d.day}/{d.year}"

def price(v):
    v = (v or "").strip().replace(",", "").replace("$", "").replace(" ", "")
    try:
        return f"${float(v):.3f}"
    except ValueError:
        return v

def fmt_chg(v):
    v = (v or "").strip().replace(" ", "").replace("%", "").replace(" ", "")
    try:
        n = float(v)
        if n > 0:  return f"+{n:.2f}%"
        if n < 0:  return f"{n:.2f}%"
        return "0.00%"
    except ValueError:
        return v + "%" if v else "0.00%"

# ── GitHub API ────────────────────────────────────────────────────────────────
def gh_get(base_url, token, path):
    req = urllib.request.Request(
        f"{base_url}{path}",
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)

def gh_put(base_url, token, path, content, message, sha):
    payload = json.dumps({
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "sha": sha,
    }).encode()
    req = urllib.request.Request(
        f"{base_url}{path}", data=payload, method="PUT",
        headers={
            "Authorization": f"token {token}",
            "Content-Type": "application/json",
        }
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)

# ── Scraper ───────────────────────────────────────────────────────────────────
async def scrape_dramexchange():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        page = await ctx.new_page()

        print("  Loading DRAMeXchange...")
        response = await page.goto(
            "https://www.dramexchange.com/",
            wait_until="networkidle",
            timeout=60000
        )
        print(f"  HTTP status: {response.status()}")

        # Save a screenshot so GitHub Actions artifacts let you see what was scraped
        await page.screenshot(path="scrape-debug.png", full_page=False)
        print("  Screenshot saved → scrape-debug.png")

        if response.status() == 403:
            await browser.close()
            raise RuntimeError("DRAMeXchange returned 403 — bot protection may have changed")

        # Wait for at least one table cell to appear
        await page.wait_for_selector("tr td", timeout=30000)
        # Extra pause for any deferred JS rendering
        await page.wait_for_timeout(1500)

        async def read_row(keyword):
            loc = page.locator("tr").filter(has_text=keyword).first
            if await loc.count() == 0:
                return None
            cells = await loc.locator("td").all()
            if len(cells) < 7:
                return None
            texts = [
                (await c.inner_text()).strip().replace(" ", " ").strip()
                for c in cells
            ]
            return {
                "date":           today_str(),
                "weekly_high":    price(texts[1]),
                "weekly_low":     price(texts[2]),
                "session_high":   price(texts[3]),
                "session_low":    price(texts[4]),
                "session_avg":    price(texts[5]),
                "session_change": fmt_chg(texts[6]),
            }

        ddr5 = await read_row("4800/5600")
        tlc  = await read_row("512Gb TLC")
        await browser.close()
        return ddr5, tlc

# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    today = today_str()
    print(f"DRAM Price Updater — {today}")

    cfg      = load_config()
    token    = cfg["github_token"]
    base_url = f"https://api.github.com/repos/{cfg['owner']}/{cfg['repo']}/contents/"

    print("  Fetching history.json from GitHub...")
    hist_file = gh_get(base_url, token, "history.json")
    hist      = json.loads(base64.b64decode(hist_file["content"].replace("\n", "")))
    hist_sha  = hist_file["sha"]

    if any(r["date"] == today for r in hist["ddr5"]):
        print(f"  DDR5 already recorded for {today}. Nothing to do.")
        return

    print("  Scraping DRAMeXchange...")
    ddr5, tlc_scraped = await scrape_dramexchange()

    if not ddr5:
        raise RuntimeError(
            "DDR5 row (4800/5600) not found on DRAMeXchange — "
            "check scrape-debug.png in Actions artifacts"
        )
    print(f"  DDR5 → {ddr5}")

    added = ["DDR5"]
    hist["ddr5"].append(ddr5)

    # TLC updates weekly; only append when ≥6 days have passed since last entry
    if tlc_scraped:
        last_tlc = hist["tlc"][-1] if hist["tlc"] else None
        if last_tlc:
            last_dt    = datetime.strptime(last_tlc["date"], "%m/%d/%Y").date()
            days_since = (date.today() - last_dt).days
            if days_since >= 6:
                hist["tlc"].append(tlc_scraped)
                added.append("512Gb TLC")
                print(f"  TLC  → {tlc_scraped}")
            else:
                print(f"  TLC skipped ({days_since}d since last entry; need ≥6).")
        else:
            hist["tlc"].append(tlc_scraped)
            added.append("512Gb TLC")
            print(f"  TLC  → {tlc_scraped}")
    else:
        print("  TLC row not found — skipped.")

    print("  Pushing history.json to GitHub...")
    gh_put(
        base_url, token,
        "history.json",
        json.dumps(hist, indent=2),
        f"prices: auto-update {today}",
        hist_sha,
    )

    print(f"  Done. Updated: {', '.join(added)}")
    print(f"  Dashboard: https://{cfg['owner']}.github.io/{cfg['repo']}/")

if __name__ == "__main__":
    asyncio.run(main())
