"""
P2: VIX-driven urgency system. Adjusts message headers and labels
based on current VIX level.
"""
from __future__ import annotations

import yfinance as yf


def get_vix() -> float | None:
    try:
        fi = yf.Ticker("^VIX").fast_info
        return float(getattr(fi, "last_price", None) or fi.get("lastPrice", 0))
    except Exception:
        return None


def urgency_banner(vix: float | None) -> str:
    """Return a banner string to prepend to messages, or empty."""
    if vix is None:
        return ""
    if vix >= 35:
        return "🚨🚨🚨 <b>极度恐慌 (VIX {:.0f})</b> 🚨🚨🚨\n\n".format(vix)
    if vix >= 25:
        return "⚡ <b>高波动警示 (VIX {:.0f})</b>\n\n".format(vix)
    return ""


def urgency_level(vix: float | None) -> str:
    """Return 'panic' / 'high' / 'normal' for decision logic."""
    if vix is None:
        return "normal"
    if vix >= 35:
        return "panic"
    if vix >= 25:
        return "high"
    return "normal"
