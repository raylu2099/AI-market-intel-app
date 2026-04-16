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

from fastapi import FastAPI, Request, HTTPException
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

app = FastAPI(title="Market Intel", version="1.0.0")

# Static files and templates
STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


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

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "watchlist": wl_quotes,
        "macro": macro_quotes,
        "radar": radar_quotes,
        "regime": regime,
        "earnings_alert": earnings,
        "china_analyses": china_analyses,
        "close_analyses": close_analyses,
        "now": datetime.now(),
    })


@app.get("/analysis/{category}/{date}", response_class=HTMLResponse)
async def view_analysis(request: Request, category: str, date: str):
    cfg = _cfg()
    path = cfg.analyses_dir(category) / f"{date}.md"
    if not path.exists():
        raise HTTPException(404, f"No analysis for {category}/{date}")
    content = path.read_text(encoding="utf-8")
    return templates.TemplateResponse("analysis.html", {
        "request": request,
        "category": category,
        "date": date,
        "content": content,
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


@app.get("/api/status", response_class=JSONResponse)
async def api_status():
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
async def api_run_slot(slot: str):
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
