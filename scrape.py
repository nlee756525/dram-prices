"""
DRAMeXchange spot price scraper
Appends daily data to history.json, regenerates index.html, pushes to GitHub Pages.
"""

import json
import os
import sys
import base64
import logging
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

URL          = "https://www.dramexchange.com/"
BASE_DIR     = Path(__file__).parent
OUTPUT_HTML  = BASE_DIR / "index.html"
HISTORY_FILE = BASE_DIR / "history.json"
CONFIG_FILE  = BASE_DIR / "config.env"
LOG_FILE     = BASE_DIR / "scraper.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

_now  = datetime.now()
TODAY = f"{_now.month}/{_now.day}/{_now.year}"


# ── config ────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    cfg = {}
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text().splitlines():
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    for key in ("GITHUB_TOKEN", "GITHUB_USER", "GITHUB_REPO"):
        if key not in cfg and os.environ.get(key):
            cfg[key] = os.environ[key]
    return cfg


# ── GitHub API ────────────────────────────────────────────────────────────────

def github_put(token: str, owner: str, repo: str, path: str,
               content: str, message: str):
    """Create or update a file in a GitHub repo via the Contents API."""
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }

    sha = ""
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            sha = json.loads(resp.read()).get("sha", "")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            log.warning("GitHub GET %s → %s", path, e.code)

    payload = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode(),
    }
    if sha:
        payload["sha"] = sha

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers=headers,
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            log.info("GitHub ← %s  %s", resp.status, path)
    except urllib.error.HTTPError as e:
        log.error("GitHub PUT %s → %s  %s", path, e.code, e.read().decode())


def push_to_github(html: str, history: dict):
    cfg   = load_config()
    token = cfg.get("GITHUB_TOKEN")
    owner = cfg.get("GITHUB_USER")
    repo  = cfg.get("GITHUB_REPO")

    if not all([token, owner, repo]):
        log.warning("GitHub push skipped — config.env missing TOKEN/USER/REPO")
        return

    date_str = datetime.now().strftime("%Y-%m-%d")
    github_put(token, owner, repo, "index.html",
               html, f"Price update {date_str}")
    github_put(token, owner, repo, "history.json",
               json.dumps(history, indent=2), f"History update {date_str}")
    log.info("Pushed to https://%s.github.io/%s/", owner, repo)


# ── helpers ───────────────────────────────────────────────────────────────────

def cell_text(cell) -> str:
    text = cell.inner_text().strip()
    if text:
        return text
    for locator in [cell, *cell.locator("*").all()[:4]]:
        for attr in ("title", "alt", "data-value"):
            val = locator.get_attribute(attr)
            if val and val.strip():
                return val.strip()
    return "N/A"


def extract_row(page, search_text: str) -> dict:
    row   = page.locator("tr").filter(has_text=search_text).first
    cells = row.locator("td").all()
    if len(cells) < 6:
        raise ValueError(f"Row '{search_text}' only has {len(cells)} cells")
    return {
        "col1": cell_text(cells[1]),
        "col2": cell_text(cells[2]),
        "col3": cell_text(cells[3]),
        "col4": cell_text(cells[4]),
        "col5": cell_text(cells[5]),
        "col6": cell_text(cells[6]) if len(cells) > 6 else "N/A",
    }


# ── scraper ───────────────────────────────────────────────────────────────────

def scrape() -> dict:
    result = {"ddr5": None, "tlc": None}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()
        log.info("Loading %s …", URL)
        try:
            page.goto(URL, wait_until="networkidle", timeout=60_000)
        except PWTimeout:
            page.wait_for_load_state("domcontentloaded")
        try:
            page.wait_for_selector("text=DRAM Spot Price", timeout=30_000)
        except PWTimeout:
            log.error("Price tables not found — aborting")
            browser.close()
            return result
        page.wait_for_timeout(2_000)

        try:
            r = extract_row(page, "4800/5600")
            result["ddr5"] = {
                "date":           TODAY,
                "weekly_high":    f"${r['col1']}",
                "weekly_low":     f"${r['col2']}",
                "session_high":   f"${r['col3']}",
                "session_low":    f"${r['col4']}",
                "session_avg":    f"${r['col5']}",
                "session_change": r["col6"],
            }
            log.info("DDR5  → %s", result["ddr5"])
        except Exception as e:
            log.error("DDR5 extraction failed: %s", e)

        try:
            r = extract_row(page, "512Gb TLC")
            result["tlc"] = {
                "date":           TODAY,
                "weekly_high":    f"${r['col1']}",
                "weekly_low":     f"${r['col2']}",
                "session_high":   f"${r['col3']}",
                "session_low":    f"${r['col4']}",
                "session_avg":    f"${r['col5']}",
                "session_change": r["col6"],
            }
            log.info("TLC   → %s", result["tlc"])
        except Exception as e:
            log.error("512Gb TLC extraction failed: %s", e)

        browser.close()
    return result


# ── history ───────────────────────────────────────────────────────────────────

def load_history() -> dict:
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    return {"ddr5": [], "tlc": []}


def save_history(history: dict):
    HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")


def append_to_history(history: dict, scraped: dict):
    for key in ("ddr5", "tlc"):
        entry = scraped.get(key)
        if not entry:
            continue
        existing_dates = {r["date"] for r in history[key]}
        if entry["date"] in existing_dates:
            log.info("%s: %s already recorded — skipping", key, entry["date"])
        else:
            history[key].append(entry)
            log.info("%s: appended %s", key, entry["date"])


# ── HTML renderer ─────────────────────────────────────────────────────────────

def change_class(val: str) -> str:
    v = val.replace("%", "").replace(" ", "")
    try:
        return "up" if float(v) > 0 else ("down" if float(v) < 0 else "flat")
    except ValueError:
        return "up" if "+" in val else ("down" if "-" in val else "flat")


def render_latest_card(entry: dict, product_type: str) -> str:
    if not entry:
        return "<div class='latest-card empty'><p>No data yet.</p></div>"
    is_dram  = product_type == "ddr5"
    card_cls = "dram" if is_dram else "nand"
    chip_cls = "chip-dram" if is_dram else "chip-nand"
    chip_txt = "DRAM" if is_dram else "NAND"
    name     = "DDR5 16Gb (2Gx8)" if is_dram else "512Gb TLC"
    sub      = "4800 / 5600 MHz"  if is_dram else "NAND Flash Wafer"
    chg      = entry.get("session_change", "N/A")
    cls      = change_class(chg)
    arrow    = "&#9650; " if cls == "up" else ("&#9660; " if cls == "down" else "")
    return (
        f"<div class='latest-card {card_cls}'>"
        f"<div class='card-top'>"
        f"<div class='card-title-group'>"
        f"<span class='chip {chip_cls}'>{chip_txt}</span>"
        f"<div><div class='card-name'>{name}</div><div class='card-sub'>{sub}</div></div>"
        f"</div>"
        f"<span class='card-date'>{entry['date']}</span>"
        f"</div>"
        f"<div class='stats-grid'>"
        f"<div class='stat'><div class='stat-label'>Weekly High</div><div class='stat-value'>{entry.get('weekly_high','N/A')}</div></div>"
        f"<div class='stat'><div class='stat-label'>Weekly Low</div><div class='stat-value'>{entry.get('weekly_low','N/A')}</div></div>"
        f"<div class='stat'><div class='stat-label'>Session High</div><div class='stat-value'>{entry.get('session_high','N/A')}</div></div>"
        f"<div class='stat'><div class='stat-label'>Session Low</div><div class='stat-value'>{entry.get('session_low','N/A')}</div></div>"
        f"<div class='stat'><div class='stat-label'>Session Average</div><div class='stat-value'>{entry.get('session_avg','N/A')}</div></div>"
        f"<div class='stat'><div class='stat-label'>Average Change</div><div class='stat-value {cls}'>{arrow}{chg}</div></div>"
        f"</div>"
        f"</div>"
    )


def render_table(rows: list) -> str:
    if not rows:
        return "<p class='empty'>No data yet.</p>"
    cols = ["Date", "Weekly High", "Weekly Low", "Session High",
            "Session Low", "Session Average", "Average Change"]
    headers = "".join(f"<th>{c}</th>" for c in cols)
    body_rows = []
    for row in reversed(rows):
        chg   = row.get("session_change", "N/A")
        cls   = change_class(chg)
        arrow = "&#9650; " if cls == "up" else ("&#9660; " if cls == "down" else "")
        cells = [f"<td>{row.get('date','')}</td>"]
        for key in ("weekly_high", "weekly_low", "session_high", "session_low", "session_avg"):
            cells.append(f"<td>{row.get(key,'N/A')}</td>")
        cells.append(f"<td class='chg {cls}'>{arrow}{chg}</td>")
        body_rows.append(f"<tr>{''.join(cells)}</tr>")
    return (
        f"<table>"
        f"<thead><tr>{headers}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        f"</table>"
    )


def build_html(history: dict) -> str:
    now     = datetime.now()
    updated = f"{now.month}/{now.day}/{now.year}"

    ddr5_rows = history.get("ddr5", [])
    tlc_rows  = history.get("tlc",  [])

    latest_ddr5 = ddr5_rows[-1] if ddr5_rows else None
    latest_tlc  = tlc_rows[-1]  if tlc_rows  else None

    ddr5_card  = render_latest_card(latest_ddr5, "ddr5")
    tlc_card   = render_latest_card(latest_tlc,  "tlc")
    ddr5_table = render_table(ddr5_rows)
    tlc_table  = render_table(tlc_rows)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>DRAM &amp; NAND Flash Spot Prices</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #0f1117; color: #e2e8f0; min-height: 100vh; padding: 2rem 1.5rem 3rem; }}
    header {{ text-align: center; margin-bottom: 2.5rem; }}
    header h1 {{ font-size: 1.75rem; font-weight: 700; color: #f8fafc; }}
    .subtitle {{ font-size: .77rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 1.2px; margin-top: .3rem; }}
    .badges {{ margin-top: .85rem; display: flex; justify-content: center; gap: .6rem; flex-wrap: wrap; }}
    .badge {{ padding: .3rem 1rem; border-radius: 999px; font-size: .78rem; font-weight: 500; }}
    .badge-date {{ background: #1e293b; border: 1px solid #334155; color: #7dd3fc; }}
    .badge-source {{ background: #0c1a2e; border: 1px solid #1d4ed8; color: #60a5fa; text-decoration: none; }}
    .badge-source:hover {{ border-color: #3b82f6; }}
    .divider-label {{ max-width: 980px; margin: 0 auto 1rem; display: flex; align-items: center; gap: .75rem; }}
    .divider-label span {{ font-size: .72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 1.5px; color: #475569; white-space: nowrap; }}
    .divider-label::after {{ content: ''; flex: 1; height: 1px; background: #1e293b; }}
    .latest-grid {{ max-width: 980px; margin: 0 auto 2.5rem; display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
    .latest-card {{ border-radius: 12px; padding: 1.25rem 1.5rem; border: 1px solid; }}
    .latest-card.dram {{ background: #0d1f3c; border-color: #1e40af; }}
    .latest-card.nand {{ background: #052e16; border-color: #166534; }}
    .latest-card.empty {{ background: #1e293b; border-color: #334155; color: #64748b; }}
    .card-top {{ display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 1rem; gap: .5rem; flex-wrap: wrap; }}
    .card-title-group {{ display: flex; align-items: center; gap: .6rem; }}
    .chip {{ padding: .22rem .65rem; border-radius: 6px; font-size: .68rem; font-weight: 700; text-transform: uppercase; letter-spacing: .5px; }}
    .chip-dram {{ background: #1d4ed8; color: #bfdbfe; }}
    .chip-nand {{ background: #065f46; color: #a7f3d0; }}
    .card-name {{ font-size: .95rem; font-weight: 600; color: #f1f5f9; }}
    .card-sub {{ font-size: .72rem; color: #64748b; margin-top: .1rem; }}
    .card-date {{ font-size: .74rem; color: #94a3b8; background: #1e293b; border: 1px solid #334155; padding: .2rem .65rem; border-radius: 999px; white-space: nowrap; }}
    .stats-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: .6rem; }}
    .stat {{ background: rgba(0,0,0,.3); border-radius: 8px; padding: .65rem .8rem; }}
    .stat-label {{ font-size: .62rem; text-transform: uppercase; letter-spacing: .5px; color: #64748b; margin-bottom: .3rem; }}
    .stat-value {{ font-size: 1rem; font-weight: 600; color: #e2e8f0; font-variant-numeric: tabular-nums; }}
    .stat-value.up   {{ color: #4ade80; }}
    .stat-value.down {{ color: #f87171; }}
    .stat-value.flat {{ color: #94a3b8; }}
    .section {{ max-width: 980px; margin: 0 auto 2.5rem; }}
    .section-header {{ display: flex; align-items: center; gap: .75rem; margin-bottom: .9rem; }}
    .section-header h2 {{ font-size: 1.05rem; font-weight: 600; color: #f1f5f9; }}
    .section-header .sub {{ font-size: .75rem; color: #64748b; }}
    .table-wrap {{ overflow-x: auto; border-radius: 10px; border: 1px solid #334155; }}
    table {{ width: 100%; border-collapse: collapse; font-size: .875rem; }}
    thead tr {{ background: #1e3a5f; }}
    thead th {{ padding: .7rem 1rem; text-align: right; font-weight: 600; font-size: .72rem; text-transform: uppercase; letter-spacing: .5px; color: #93c5fd; white-space: nowrap; border-bottom: 2px solid #334155; }}
    thead th:first-child {{ text-align: left; }}
    tbody tr:nth-child(odd)  {{ background: #141b2d; }}
    tbody tr:nth-child(even) {{ background: #1a2438; }}
    tbody tr:hover           {{ background: #1e3050; }}
    tbody tr:first-child td  {{ color: #f1f5f9; font-weight: 500; }}
    tbody tr:last-child td   {{ border-bottom: none; }}
    tbody td {{ padding: .6rem 1rem; text-align: right; border-bottom: 1px solid #1e293b; font-variant-numeric: tabular-nums; color: #cbd5e1; white-space: nowrap; }}
    tbody td:first-child {{ text-align: left; color: #94a3b8; font-size: .82rem; }}
    .chg {{ font-weight: 700; }}
    .chg.up   {{ color: #4ade80; }}
    .chg.down {{ color: #f87171; }}
    .chg.flat {{ color: #94a3b8; }}
    .empty {{ color: #475569; font-size: .85rem; padding: 1rem; }}
    footer {{ text-align: center; font-size: .72rem; color: #475569; margin-top: 1rem; }}
    footer a {{ color: #60a5fa; text-decoration: none; }}
    @media (max-width: 600px) {{
      .latest-grid {{ grid-template-columns: 1fr; }}
      .stats-grid  {{ grid-template-columns: repeat(2, 1fr); }}
    }}
  </style>
</head>
<body>
<header>
  <div class="subtitle">Spot Price Report</div>
  <h1>DRAM &amp; NAND Flash Prices</h1>
  <div class="badges">
    <span class="badge badge-date">Last updated: {updated}</span>
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
  <div class="section-header">
    <span class="chip chip-dram">DRAM</span>
    <h2>DDR5 16Gb (2Gx8)</h2>
    <span class="sub">4800 / 5600 MHz</span>
  </div>
  <div class="table-wrap">{ddr5_table}</div>
</div>
<div class="section">
  <div class="section-header">
    <span class="chip chip-nand">NAND</span>
    <h2>512Gb TLC</h2>
    <span class="sub">NAND Flash Wafer</span>
  </div>
  <div class="table-wrap">{tlc_table}</div>
</div>
<footer><p>Prices in USD · Source: <a href="https://www.dramexchange.com/" target="_blank" rel="noopener">DRAMeXchange / TrendForce</a></p></footer>
</body>
</html>"""


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("=== DRAMeXchange scraper started ===")
    history = load_history()
    scraped = scrape()
    append_to_history(history, scraped)
    save_history(history)
    html = build_html(history)
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    log.info("Dashboard written → %s", OUTPUT_HTML)
    push_to_github(html, history)
    log.info("=== Done ===")
