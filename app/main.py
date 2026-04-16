"""
FastAPI web application for market-intel.

Pages:
- / — Dashboard: current market snapshot + latest analyses
- /analysis/<category>/<date> — View a specific daily analysis
- /history — Browse past analyses and archived articles
- /settings — View/edit watchlist and configuration
- /api/run/<slot> — Trigger a slot manually (POST)
- /api/status — System health status (JSON)
"""
from __future__ import annotations

import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Add project root to path so we can import intel.*
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from intel.config import load_config
from intel.prices import MACRO_TICKERS, RADAR_TICKERS, fetch_quotes, format_watchlist
from intel.technicals import compute_technicals
from intel.valuations import fetch_valuations
from intel.earnings import fetch_all_earnings
from intel.macro_regime import compute_regime
from intel.sentiment import fetch_sentiment
from intel.storage import load_recent_analyses
from intel.events import upcoming_earnings, upcoming_macro_events
from intel.cost_tracker import load_weekly_costs
from intel.pnl_tracker import load_all_positions, compute_pnl

from .auth import verify_api_key
from .tooltips import tip, TOOLTIPS

app = FastAPI(title="Market Intel", version="1.0.0")

# S2: CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# S3: Valid slot names
VALID_SLOTS = {
    "premarket", "open", "midday", "close",
    "stocks_pre", "stocks_post", "china_open",
    "weekly_review", "watchdog",
}

# Static files and templates
STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
# Make tooltips available in all templates
templates.env.globals["tip"] = tip
templates.env.globals["TOOLTIPS"] = TOOLTIPS


def _cfg():
    return load_config()


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    cfg = _cfg()

    # Market data
    wl_quotes = fetch_quotes(cfg.watchlist)
    macro_quotes = fetch_quotes(MACRO_TICKERS)
    radar_quotes = fetch_quotes(RADAR_TICKERS)
    regime = compute_regime()
    earnings = upcoming_earnings(cfg)

    # Latest analyses
    china_analyses = load_recent_analyses(cfg, "china", 3)
    close_analyses = load_recent_analyses(cfg, "market_close", 3)

    # U2: Extract today's key insight from latest analysis
    key_insight = ""
    for analyses in [close_analyses, china_analyses]:
        if analyses:
            _, content = analyses[-1]
            # Extract first 2-3 sentences from macro narrative section
            for line in content.split("\n"):
                line = line.strip()
                if len(line) > 50 and not line.startswith(("━", "<b>", "📝", "💹", "🎯", "#")):
                    key_insight = line[:300]
                    if len(line) > 300:
                        key_insight += "…"
                    break
            if key_insight:
                break

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "watchlist": wl_quotes,
        "macro": macro_quotes,
        "radar": radar_quotes,
        "regime": regime,
        "earnings_alert": earnings,
        "china_analyses": china_analyses,
        "close_analyses": close_analyses,
        "key_insight": key_insight,
        "valid_slots": sorted(VALID_SLOTS),
        "now": datetime.now(),
    })


def _parse_sections(content: str) -> list[dict]:
    """U7: Parse analysis Markdown into collapsible sections by emoji headers."""
    import re
    # Match section headers: lines with emoji + bold tag
    markers = ["📝", "💹", "🎯", "🔀", "🌐", "📋", "🛡️", "🔗", "📊"]
    lines = content.split("\n")
    sections = []
    current_title = None
    current_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        # Detect section header: contains an emoji marker + bold or all caps title
        is_header = any(m in stripped[:5] for m in markers) and ("<b>" in stripped or "**" in stripped)
        if is_header:
            if current_title:
                sections.append({"title": current_title, "content": "\n".join(current_lines).strip()})
            # Clean title: strip HTML tags and markdown
            title = re.sub(r"<[^>]+>", "", stripped).replace("**", "").strip()
            current_title = title
            current_lines = []
        else:
            current_lines.append(line)
    if current_title:
        sections.append({"title": current_title, "content": "\n".join(current_lines).strip()})
    return sections


def _neighbor_dates(cfg, category: str, date: str) -> tuple[str | None, str | None]:
    """Return (prev_date, next_date) for navigation."""
    d = cfg.analyses_dir(category)
    if not d.exists():
        return None, None
    dates = sorted(p.stem for p in d.glob("*.md"))
    try:
        idx = dates.index(date)
    except ValueError:
        return None, None
    prev_d = dates[idx - 1] if idx > 0 else None
    next_d = dates[idx + 1] if idx + 1 < len(dates) else None
    return prev_d, next_d


@app.get("/analysis/{category}/{date}", response_class=HTMLResponse)
async def view_analysis(request: Request, category: str, date: str):
    cfg = _cfg()
    path = cfg.analyses_dir(category) / f"{date}.md"
    if not path.exists():
        raise HTTPException(404, f"No analysis for {category}/{date}")
    content = path.read_text(encoding="utf-8")
    sections = _parse_sections(content)
    prev_d, next_d = _neighbor_dates(cfg, category, date)
    return templates.TemplateResponse("analysis.html", {
        "request": request,
        "category": category,
        "date": date,
        "content": content,
        "sections": sections,
        "prev_url": f"/analysis/{category}/{prev_d}" if prev_d else "",
        "next_url": f"/analysis/{category}/{next_d}" if next_d else "",
        "now": datetime.now(),
    })


@app.get("/compare", response_class=HTMLResponse)
async def compare(request: Request, a: str = "", b: str = ""):
    """Side-by-side analysis comparison. Params: a=category/date, b=category/date"""
    cfg = _cfg()
    def _load(ref: str):
        try:
            cat, dt = ref.split("/")
            p = cfg.analyses_dir(cat) / f"{dt}.md"
            return cat, dt, p.read_text(encoding="utf-8") if p.exists() else "Not found"
        except Exception:
            return "—", "—", "Invalid reference"
    a_cat, a_dt, a_content = _load(a)
    b_cat, b_dt, b_content = _load(b)
    return templates.TemplateResponse("compare.html", {
        "request": request,
        "a_category": a_cat, "a_date": a_dt, "a_content": a_content,
        "b_category": b_cat, "b_date": b_dt, "b_content": b_content,
        "now": datetime.now(),
    })


@app.get("/history", response_class=HTMLResponse)
async def history(request: Request):
    cfg = _cfg()
    entries = []
    for category in ("china", "market_close", "weekly_review"):
        d = cfg.analyses_dir(category)
        if d.exists():
            for p in sorted(d.glob("*.md"), reverse=True)[:30]:
                entries.append({
                    "category": category,
                    "date": p.stem,
                    "size": p.stat().st_size,
                })
    entries.sort(key=lambda x: x["date"], reverse=True)
    return templates.TemplateResponse("history.html", {
        "request": request,
        "entries": entries,
        "now": datetime.now(),
    })


@app.get("/stocks", response_class=HTMLResponse)
async def stocks(request: Request):
    cfg = _cfg()
    wl_quotes = fetch_quotes(cfg.watchlist)
    tech = compute_technicals(cfg.watchlist)
    vals = fetch_valuations(cfg.watchlist)
    earns = fetch_all_earnings(cfg)
    sentiment = fetch_sentiment(cfg.watchlist)

    stock_data = []
    for i, (ticker, name) in enumerate(cfg.watchlist):
        stock_data.append({
            "ticker": ticker,
            "name": name,
            "quote": wl_quotes[i] if i < len(wl_quotes) else None,
            "tech": tech[i] if i < len(tech) else None,
            "val": vals[i] if i < len(vals) else None,
            "earn": earns[i] if i < len(earns) else None,
            "short": sentiment.shorts[i] if i < len(sentiment.shorts) else None,
        })

    return templates.TemplateResponse("stocks.html", {
        "request": request,
        "stocks": stock_data,
        "now": datetime.now(),
    })


@app.get("/settings", response_class=HTMLResponse)
async def settings(request: Request):
    """U5: Read-only settings page."""
    cfg = _cfg()
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "cfg": cfg,
        "now": datetime.now(),
    })


# --- API endpoints (S1: authenticated) ---

@app.get("/api/status", response_class=JSONResponse)
async def api_status(api_key: str = Depends(verify_api_key)):
    cfg = _cfg()
    costs = load_weekly_costs(cfg, 7)
    positions = load_all_positions(cfg, 7)
    return {
        "status": "ok",
        "watchlist": [t for t, _ in cfg.watchlist],
        "weekly_costs": costs,
        "active_positions": len(positions),
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/api/run/{slot}")
async def api_run_slot(slot: str, api_key: str = Depends(verify_api_key)):
    # S3: Input validation
    if slot not in VALID_SLOTS:
        raise HTTPException(
            400, f"Invalid slot '{slot}'. Valid: {sorted(VALID_SLOTS)}"
        )
    cfg = _cfg()
    runner = PROJECT_ROOT / "bin" / "run-slot.sh"
    if not runner.exists():
        raise HTTPException(500, "run-slot.sh not found")
    try:
        result = subprocess.run(
            [str(runner), slot],
            capture_output=True, text=True, timeout=600,
            cwd=str(PROJECT_ROOT),
        )
        return {
            "slot": slot,
            "exit_code": result.returncode,
            "stdout": result.stdout[-500:] if result.stdout else "",
            "stderr": result.stderr[-500:] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {"slot": slot, "exit_code": -1, "error": "timeout"}
