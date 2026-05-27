#!/usr/bin/env python3
"""
DRAM Price Updater
Scrapes DRAMeXchange with a real browser (Playwright) to avoid 403,
then pushes updates directly to GitHub via the API.

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

Schedule (Windows Task Scheduler):
    Action: python C:\path\to\scrape.py
    Trigger: Daily, weekdays, 9:00 AM

Schedule (Mac/Linux cron):
    0 9 * * 1-5 /usr/bin/python3 /path/to/scrape.py >> /path/to/scrape.log 2>&1
"""

import asyncio
import json
import base64
import urllib.request
import os
from datetime import date, datetime
from pathlib import Path
from playwright.async_api import async_playwright

# ── Config ───────────────────────────────────────────────────────────────────
def load_config():
    config_path = Path(__file__).parent / "config.json"
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    # Fall back to environment variables
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

# ── Formatters ───────────────────────────────────────────────────────────────
def today_str():
    d = date.today()
    return f"{d.month}/{d.day}/{d.year}"

def price(v):
    v = (v or "").strip().replace(",", "").replace("$", "")
    try:
        return f"${float(v):.3f}"
    except ValueError:
        return v

def fmt_chg(v):
    v = (v or "").strip().replace(" ", "").replace("%", "")
    try:
        n = float(v)
        if n > 0:  return f"+{n:.2f}%"
        if n < 0:  return f"{n:.2f}%"
        return "0.00%"
    except ValueError:
        return v + "%"

def chg_class(v):
    try:
        n = float((v or "").strip().replace("%", "").replace("+", ""))
        if n > 0:  return "up"
        if n < 0:  return "down"
        return "flat"
    except ValueError:
        if "+" in (v or ""):  return "up"
        if "-" in (v or ""):  return "down"
        return "flat"

# ── HTML builders ─────────────────────────────────────────────────────────────
def row_html(r):
    c = chg_class(r["session_change"])
    arr = "&#9650; " if c == "up" else "&#9660; " if c == "down" else ""
    return (f"<tr><td>{r['date']}</td><td>{r['weekly_high']}</td>"
            f"<td>{r['weekly_low']}</td><td>{r['session_high']}</td>"
            f"<td>{r['session_low']}</td><td>{r['session_avg']}</td>"
            f"<td class='chg {c}'>{arr}{r['session_change']}</td></tr>")

def card_html(kind, chip_cls, chip_lbl, name, sub, r):
    c = chg_class(r["session_change"])
    arr = "&#9650; " if c == "up" else "&#9660; " if c == "down" else ""
    return (
        f"<div class='latest-card {kind}'>"
        f"<div class='card-top'><div class='card-title-group'>"
        f"<span class='chip chip-{chip_cls}'>{chip_lbl}</span>"
        f"<div><div class='card-name'>{name}</div><div class='card-sub'>{sub}</div></div>"
        f"</div><span class='card-date'>{r['date']}</span></div>"
        f"<div class='stats-grid'>"
        f"<div class='stat'><div class='stat-label'>Weekly High</div><div class='stat-value'>{r['weekly_high']}</div></div>"
        f"<div class='stat'><div class='stat-label'>Weekly Low</div><div class='stat-value'>{r['weekly_low']}</div></div>"
        f"<div class='stat'><div class='stat-label'>Session High</div><div class='stat-value'>{r['session_high']}</div></div>"
        f"<div class='stat'><div class='stat-label'>Session Low</div><div class='stat-value'>{r['session_low']}</div></div>"
        f"<div class='stat'><div class='stat-label'>Session Average</div><div class='stat-value'>{r['session_avg']}</div></div>"
        f"<div class='stat'><div class='stat-label'>Average Change</div>"
        f"<div class='stat-value {c}'>{arr}{r['session_change']}</div></div>"
        f"</div></div>"
    )

def build_html(hist, today):
    ld = hist["ddr5"][-1]
    lt = hist["tlc"][-1]
    ddr5_rows = "".join(row_html(r) for r in reversed(hist["ddr5"]))
    tlc_rows  = "".join(row_html(r) for r in reversed(hist["tlc"]))
    ddr5_card = card_html("dram","dram","DRAM","DDR5 16Gb (2Gx8)","4800 / 5600 MHz", ld)
    tlc_card  = card_html("nand","nand","NAND","512Gb TLC","NAND Flash Wafer", lt)

    CSS = ("*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}"
           "body{font-family:'Segoe UI',system-ui,sans-serif;background:#0f1117;color:#e2e8f0;min-height:100vh;padding:2rem 1.5rem 3rem}"
           "header{text-align:center;margin-bottom:2.5rem}"
           "header h1{font-size:1.75rem;font-weight:700;color:#f8fafc}"
           ".subtitle{font-size:.77rem;color:#94a3b8;text-transform:uppercase;letter-spacing:1.2px;margin-top:.3rem}"
           ".badges{margin-top:.85rem;display:flex;justify-content:center;gap:.6rem;flex-wrap:wrap}"
           ".badge{padding:.3rem 1rem;border-radius:999px;font-size:.78rem;font-weight:500}"
           ".badge-date{background:#1e293b;border:1px solid #334155;color:#7dd3fc}"
           ".badge-source{background:#0c1a2e;border:1px solid #1d4ed8;color:#60a5fa;text-decoration:none}"
           ".badge-source:hover{border-color:#3b82f6}"
           ".divider-label{max-width:980px;margin:0 auto 1rem;display:flex;align-items:center;gap:.75rem}"
           ".divider-label span{font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:#475569;white-space:nowrap}"
           ".divider-label::after{content:'';flex:1;height:1px;background:#1e293b}"
           ".latest-grid{max-width:980px;margin:0 auto 2.5rem;display:grid;grid-template-columns:1fr 1fr;gap:1rem}"
           ".latest-card{border-radius:12px;padding:1.25rem 1.5rem;border:1px solid}"
           ".latest-card.dram{background:#0d1f3c;border-color:#1e40af}"
           ".latest-card.nand{background:#052e16;border-color:#166534}"
           ".latest-card.empty{background:#1e293b;border-color:#334155;color:#64748b}"
           ".card-top{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:1rem;gap:.5rem;flex-wrap:wrap}"
           ".card-title-group{display:flex;align-items:center;gap:.6rem}"
           ".chip{padding:.22rem .65rem;border-radius:6px;font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.5px}"
           ".chip-dram{background:#1d4ed8;color:#bfdbfe}"
           ".chip-nand{background:#065f46;color:#a7f3d0}"
           ".card-name{font-size:.95rem;font-weight:600;color:#f1f5f9}"
           ".card-sub{font-size:.72rem;color:#64748b;margin-top:.1rem}"
           ".card-date{font-size:.74rem;color:#94a3b8;background:#1e293b;border:1px solid #334155;padding:.2rem .65rem;border-radius:999px;white-space:nowrap}"
           ".stats-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:.6rem}"
           ".stat{background:rgba(0,0,0,.3);border-radius:8px;padding:.65rem .8rem}"
           ".stat-label{font-size:.62rem;text-transform:uppercase;letter-spacing:.5px;color:#64748b;margin-bottom:.3rem}"
           ".stat-value{font-size:1rem;font-weight:600;color:#e2e8f0;font-variant-numeric:tabular-nums}"
           ".stat-value.up{color:#4ade80}.stat-value.down{color:#f87171}.stat-value.flat{color:#94a3b8}"
           ".section{max-width:980px;margin:0 auto 2.5rem}"
           ".section-header{display:flex;align-items:center;gap:.75rem;margin-bottom:.9rem}"
           ".section-header h2{font-size:1.05rem;font-weight:600;color:#f1f5f9}"
           ".section-header .sub{font-size:.75rem;color:#64748b}"
           ".table-wrap{overflow-x:auto;border-radius:10px;border:1px solid #334155}"
           "table{width:100%;border-collapse:collapse;font-size:.875rem}"
           "thead tr{background:#1e3a5f}"
           "thead th{padding:.7rem 1rem;text-align:right;font-weight:600;font-size:.72rem;text-transform:uppercase;letter-spacing:.5px;color:#93c5fd;white-space:nowrap;border-bottom:2px solid #334155}"
           "thead th:first-child{text-align:left}"
           "tbody tr:nth-child(odd){background:#141b2d}"
           "tbody tr:nth-child(even){background:#1a2438}"
           "tbody tr:hover{background:#1e3050}"
           "tbody tr:first-child td{color:#f1f5f9;font-weight:500}"
           "tbody tr:last-child td{border-bottom:none}"
           "tbody td{padding:.6rem 1rem;text-align:right;border-bottom:1px solid #1e293b;font-variant-numeric:tabular-nums;color:#cbd5e1;white-space:nowrap}"
           "tbody td:first-child{text-align:left;color:#94a3b8;font-size:.82rem}"
           ".chg{font-weight:700}.chg.up{color:#4ade80}.chg.down{color:#f87171}.chg.flat{color:#94a3b8}"
           ".empty{color:#475569;font-size:.85rem;padding:1rem}"
           "footer{text-align:center;font-size:.72rem;color:#475569;margin-top:1rem}"
           "footer a{color:#60a5fa;text-decoration:none}"
           "@media(max-width:600px){.latest-grid{grid-template-columns:1fr}.stats-grid{grid-template-columns:repeat(2,1fr)}}")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>DRAM &amp; NAND Flash Spot Prices</title>
  <style>{CSS}</style>
</head>
<body>
<header>
  <div class="subtitle">Spot Price Report</div>
  <h1>DRAM &amp; NAND Flash Prices</h1>
  <div class="badges">
    <span class="badge badge-date">Last updated: {today}</span>
    <a class="badge badge-source" href="https://www.dramexchange.com/" target="_blank" rel="noopener">DRAMeXchange / TrendForce</a>
  </div>
</header>
<div class="divider-label"><span>Latest Update</span></div>
<div class="latest-grid">
{ddr5_card}
{tlc_card}
</div>
<div class="divider-label"><span>Price History</span></div>
<div class="section">
  <div class="section-header"><span class="chip chip-dram">DRAM</span><h2>DDR5 16Gb (2Gx8)</h2><span class="sub">4800 / 5600 MHz</span></div>
  <div class="table-wrap"><table><thead><tr><th>Date</th><th>Weekly High</th><th>Weekly Low</th><th>Session High</th><th>Session Low</th><th>Session Average</th><th>Average Change</th></tr></thead><tbody>{ddr5_rows}</tbody></table></div>
</div>
<div class="section">
  <div class="section-header"><span class="chip chip-nand">NAND</span><h2>512Gb TLC</h2><span class="sub">NAND Flash Wafer</span></div>
  <div class="table-wrap"><table><thead><tr><th>Date</th><th>Weekly High</th><th>Weekly Low</th><th>Session High</th><th>Session Low</th><th>Session Average</th><th>Average Change</th></tr></thead><tbody>{tlc_rows}</tbody></table></div>
</div>
<footer><p>Prices in USD · Source: <a href="https://www.dramexchange.com/" target="_blank" rel="noopener">DRAMeXchange / TrendForce</a></p></footer>
</body>
</html>"""

# ── GitHub API ────────────────────────────────────────────────────────────────
def gh_get(base_url, token, path):
    req = urllib.request.Request(
        f"{base_url}{path}",
        headers={"Authorization": f"token {token}",
                 "Accept": "application/vnd.github.v3+json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)

def gh_put(base_url, token, path, content, message, sha):
    payload = json.dumps({
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "sha": sha
    }).encode()
    req = urllib.request.Request(
        f"{base_url}{path}", data=payload, method="PUT",
        headers={"Authorization": f"token {token}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)

# ── Scraper ───────────────────────────────────────────────────────────────────
async def scrape_dramexchange():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"),
            viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()

        print("  Loading DRAMeXchange...")
        await page.goto("https://www.dramexchange.com/",
                        wait_until="networkidle", timeout=45000)

        async def read_row(keyword):
            loc = page.locator("tr").filter(has_text=keyword).first
            if await loc.count() == 0:
                return None
            cells = await loc.locator("td").all()
            if len(cells) < 7:
                return None
            return {
                "date":           today_str(),
                "weekly_high":    price(await cells[1].inner_text()),
                "weekly_low":     price(await cells[2].inner_text()),
                "session_high":   price(await cells[3].inner_text()),
                "session_low":    price(await cells[4].inner_text()),
                "session_avg":    price(await cells[5].inner_text()),
                "session_change": fmt_chg(await cells[6].inner_text()),
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

    print("  Fetching index.html SHA...")
    idx_sha = gh_get(base_url, token, "index.html")["sha"]

    if any(r["date"] == today for r in hist["ddr5"]):
        print(f"  DDR5 already recorded for {today}. Nothing to do.")
        return

    print("  Scraping DRAMeXchange...")
    ddr5, tlc_scraped = await scrape_dramexchange()

    if not ddr5:
        print("  ERROR: DDR5 row not found on page. Aborting.")
        return
    print(f"  DDR5 → {ddr5}")

    added = ["DDR5"]
    hist["ddr5"].append(ddr5)

    if tlc_scraped:
        last_tlc_date = hist["tlc"][-1]["date"] if hist["tlc"] else None
        if last_tlc_date:
            last_dt    = datetime.strptime(last_tlc_date, "%m/%d/%Y").date()
            days_since = (date.today() - last_dt).days
            if days_since >= 6:
                hist["tlc"].append(tlc_scraped)
                added.append("512Gb TLC")
                print(f"  TLC  → {tlc_scraped}")
            else:
                print(f"  TLC skipped ({days_since} days since last entry, need ≥6).")
        else:
            hist["tlc"].append(tlc_scraped)
            added.append("512Gb TLC")
            print(f"  TLC  → {tlc_scraped}")
    else:
        print("  TLC row not found on page — skipped.")

    print("  Pushing to GitHub...")
    gh_put(base_url, token, "history.json",
           json.dumps(hist, indent=2), f"prices: add {today}", hist_sha)
    gh_put(base_url, token, "index.html",
           build_html(hist, today), f"site: update {today}", idx_sha)

    print(f"  Done. Updated: {', '.join(added)}")
    print(f"  Live at: https://{cfg['owner']}.github.io/{cfg['repo']}/")

if __name__ == "__main__":
    asyncio.run(main())
