"""
Event calendar: upcoming earnings for watchlist + macro events.
Two sources: yfinance (earnings) + Perplexity (macro calendar).
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import date, timedelta

from .config import Config
from .cost_tracker import record_cost
from .search import PPLX_ENDPOINT


def upcoming_earnings(cfg: Config, horizon_days: int = 7) -> str:
    """Check yfinance for upcoming watchlist earnings within horizon."""
    try:
        import yfinance as yf
    except ImportError:
        return "（yfinance 未安装，无法查询财报日历）"

    today = date.today()
    end = today + timedelta(days=horizon_days)
    hits = []
    for ticker, name in cfg.watchlist:
        try:
            cal = yf.Ticker(ticker).calendar
            if isinstance(cal, dict):
                ed = cal.get("Earnings Date")
                if isinstance(ed, list) and ed:
                    ed = ed[0]
                if ed and today <= ed <= end:
                    hits.append(
                        f"• <b>{name}</b> ({ticker}): {ed.strftime('%a %m/%d')}"
                    )
        except Exception:
            continue
    if not hits:
        return "未来 7 天 watchlist 无财报"
    return "\n".join(hits)


def upcoming_macro_events(cfg: Config) -> str:
    """Ask Perplexity for this week's key US macro events. Cheap sonar call."""
    from .timeutil import now_pt
    today = now_pt().strftime("%Y-%m-%d")
    prompt = (
        f"从今天（{today}）到本周日，美国有哪些关键宏观事件？"
        "重点包括：CPI、PPI、PCE、非农、零售销售、ISM PMI、FOMC 会议、Fed 官员讲话。"
        "每条格式：『MM/DD (周X) HH:MM ET — 事件名称』。最多 8 条。"
        "严禁前后说明、预期值、详细分析。只输出列表。若无事件，输出『无』。"
    )
    body = {
        "model": cfg.pplx_model_search,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 300,
        "temperature": 0.1,
        "search_recency_filter": "week",
        "web_search_options": {"search_context_size": "low"},
    }
    req = urllib.request.Request(
        PPLX_ENDPOINT,
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {cfg.perplexity_api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        cost = data.get("usage", {}).get("cost", {}).get("total_cost", 0)
        if cost:
            record_cost("perplexity_events", cost)
            print(f"[cost] macro_events: ${cost:.5f}", file=sys.stderr)
        return (
            data.get("choices", [{}])[0]
            .get("message", {}).get("content", "")
        ).strip() or "无"
    except Exception as e:
        print(f"[events] macro calendar failed: {e}", file=sys.stderr)
        return f"[查询失败: {e}]"


def format_event_calendar(cfg: Config) -> str:
    """Combined event calendar block for Telegram."""
    parts = [
        "📅 <b>事件日历</b>",
        "",
        "<b>财报 (Watchlist, 未来 7 天)</b>",
        upcoming_earnings(cfg),
        "",
        "<b>宏观事件 (本周)</b>",
        upcoming_macro_events(cfg),
    ]
    return "\n".join(parts)
