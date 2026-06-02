#!/usr/bin/env python3
"""
DRAM Price Updater
Scrapes DRAMeXchange with a real browser (Playwright) to avoid 403,
then updates history.json via the GitHub Contents API.
"""

import asyncio
import json
import base64
import urllib.request
import os
import traceback
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
        raise RuntimeError("No GitHub token found. Set GITHUB_TOKEN env var or create config.json.")
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
    v = (v or "").strip().replace(",", "").replace("$", "").replace("\xa0", "").replace(" ", "")
    try:
        return f"${float(v):.3f}"
    except ValueError:
        return v

def fmt_chg(v):
    v = (v or "").strip().replace(" ", "").replace("%", "").replace("\xa0", "")
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
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
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
        headers={"Authorization": f"token {token}", "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)

# ── Scraper ───────────────────────────────────────────────────────────────────
async def scrape_dramexchange():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ]
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Upgrade-Insecure-Requests": "1",
            }
        )
        await ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        page = await ctx.new_page()

        # ── Navigate ──────────────────────────────────────────────────────────
        print("  Loading DRAMeXchange...")
        import playwright
        print(f"  Playwright version: {playwright.__version__}")

        nav_ok = False
        try:
            response = await page.goto(
                "https://www.dramexchange.com/",
                wait_until="load",
                timeout=45000
            )
            status = response.status if response is not None else "None"
            print(f"  HTTP status: {status}")
            nav_ok = True
        except Exception as e:
            traceback.print_exc()
            print(f"  Navigation error type: {type(e).__name__}")
            print(f"  Navigation error: {e}")
        finally:
            await page.screenshot(path="scrape-debug.png", full_page=True)
            print("  Screenshot saved.")

        if not nav_ok:
            raise RuntimeError("Navigation failed — see scrape-debug.png")

        # ── Debug: print page title and all row text ──────────────────────────
        title = await page.title()
        print(f"  Page title: {title!r}")

        # Print every table row's text so we can see exactly what's there
        all_rows = await page.evaluate("""() => {
            const rows = Array.from(document.querySelectorAll('tr'));
            return rows.map(r => r.innerText.replace(/\\s+/g, ' ').trim()).filter(t => t.length > 5);
        }""")
        print(f"  Total rows found: {len(all_rows)}")
        for i, row in enumerate(all_rows[:30]):
            print(f"    row[{i:02d}]: {row[:120]}")

        # ── Wait for data table ───────────────────────────────────────────────
        try:
            await page.wait_for_selector("tr td", timeout=25000)
        except Exception:
            raise RuntimeError("No <tr><td> found within 25s — check scrape-debug.png")

        await page.wait_for_timeout(2000)

        # Re-take screenshot after JS finishes
        await page.screenshot(path="scrape-debug.png", full_page=True)

        # ── Extract rows ──────────────────────────────────────────────────────
        async def read_row(*keywords):
            """Try each keyword in order; return the first matching row."""
            for kw in keywords:
                loc = page.locator("tr").filter(has_text=kw).first
                if await loc.count() > 0:
                    cells = await loc.locator("td").all()
                    if len(cells) >= 7:
                        texts = [(await c.inner_text()).strip().replace("\xa0", " ").strip()
                                 for c in cells]
                        print(f"  Matched '{kw}': {texts[:7]}")
                        return {
                            "date":           today_str(),
                            "weekly_high":    price(texts[1]),
                            "weekly_low":     price(texts[2]),
                            "session_high":   price(texts[3]),
                            "session_low":    price(texts[4]),
                            "session_avg":    price(texts[5]),
                            "session_change": fmt_chg(texts[6]),
                        }
                    print(f"  '{kw}' row found but only {len(cells)} cells")
            print(f"  None of {keywords} matched any row")
            return None

        ddr5 = await read_row("4800/5600", "4800 / 5600", "DDR5 16Gb")
        tlc  = await read_row("512Gb TLC", "512GB TLC", "512 Gb TLC")
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
            "DDR5 row not found — see the row dump above and scrape-debug.png to identify the correct text"
        )
    print(f"  DDR5 → {ddr5}")

    added = ["DDR5"]
    hist["ddr5"].append(ddr5)

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
                print(f"  TLC skipped ({days_since}d since last; need ≥6).")
        else:
            hist["tlc"].append(tlc_scraped)
            added.append("512Gb TLC")
            print(f"  TLC  → {tlc_scraped}")
    else:
        print("  TLC row not found — skipped.")

    print("  Pushing history.json to GitHub...")
    gh_put(
        base_url, token, "history.json",
        json.dumps(hist, indent=2),
        f"prices: auto-update {today}",
        hist_sha,
    )
    print(f"  Done. Updated: {', '.join(added)}")

if __name__ == "__main__":
    asyncio.run(main())
