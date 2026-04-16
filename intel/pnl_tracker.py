"""
Q12: P&L tracker. Parses [POSITIONS] blocks from saved analyses,
fetches current prices, and computes unrealized P&L for weekly review.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass

import yfinance as yf

from .config import Config
from .storage import load_recent_analyses


@dataclass
class TrackedPosition:
    ticker: str
    direction: str      # LONG / SHORT / NEUTRAL
    entry_price: float
    date: str
    horizon: str
    thesis: str
    size_pct: str = ""          # e.g. "5%"
    status: str = "OPEN"       # OPEN / WATCH / CLOSED
    risk_weight: str = ""      # LOW / MED / HIGH
    stop_price: float | None = None
    current_price: float | None = None
    pnl_pct: float | None = None
    source_category: str = ""


def parse_positions_from_analysis(text: str, category: str) -> list[TrackedPosition]:
    """Extract [POSITIONS] blocks from an analysis markdown."""
    pattern = r'\[POSITIONS\](.*?)\[/POSITIONS\]'
    matches = re.findall(pattern, text, re.DOTALL)
    positions = []
    for block in matches:
        for line in block.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("TICKER") or line.startswith("---"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 5:
                try:
                    # Support both old (6-field) and new (10-field) format
                    if len(parts) >= 10:
                        # New format: TICKER|DIR|SIZE|ENTRY|DATE|STATUS|RISK|HORIZON|STOP|THESIS
                        stop_raw = parts[8].strip()
                        positions.append(TrackedPosition(
                            ticker=parts[0],
                            direction=parts[1].upper(),
                            size_pct=parts[2],
                            entry_price=float(parts[3]),
                            date=parts[4],
                            status=parts[5].upper(),
                            risk_weight=parts[6].upper(),
                            horizon=parts[7],
                            stop_price=float(stop_raw) if stop_raw != "-" else None,
                            thesis=parts[9] if len(parts) > 9 else "",
                            source_category=category,
                        ))
                    else:
                        # Legacy 6-field format
                        positions.append(TrackedPosition(
                            ticker=parts[0],
                            direction=parts[1].upper(),
                            entry_price=float(parts[2]),
                            date=parts[3],
                            horizon=parts[4],
                            thesis=parts[5] if len(parts) > 5 else "",
                            source_category=category,
                        ))
                except (ValueError, IndexError):
                    continue
    return positions


def load_all_positions(cfg: Config, days: int = 7) -> list[TrackedPosition]:
    """Load all positions from the last N days of analyses."""
    all_pos = []
    for category in ("china", "market_close"):
        analyses = load_recent_analyses(cfg, category, days)
        for date_str, content in analyses:
            positions = parse_positions_from_analysis(content, category)
            all_pos.extend(positions)
    return all_pos


def compute_pnl(positions: list[TrackedPosition]) -> list[TrackedPosition]:
    """Fetch current prices and compute unrealized P&L."""
    tickers = list(set(p.ticker for p in positions if p.direction != "NEUTRAL"))
    prices = {}
    for t in tickers:
        try:
            fi = yf.Ticker(t).fast_info
            price = getattr(fi, "last_price", None)
            if price:
                prices[t] = float(price)
        except Exception:
            continue

    for p in positions:
        if p.direction == "NEUTRAL" or p.ticker not in prices:
            continue
        current = prices[p.ticker]
        p.current_price = current
        if p.direction == "LONG":
            p.pnl_pct = (current - p.entry_price) / p.entry_price * 100
        elif p.direction == "SHORT":
            p.pnl_pct = (p.entry_price - current) / p.entry_price * 100

    return positions


def format_pnl_review(positions: list[TrackedPosition]) -> str:
    """Format P&L review for weekly_review slot."""
    if not positions:
        return "📊 <b>仓位 P&L 追踪</b>\n本周无结构化仓位记录。"

    lines = ["📊 <b>仓位 P&L 追踪</b>"]
    wins = 0
    losses = 0
    stopped = 0
    for p in sorted(positions, key=lambda x: x.date):
        if p.status == "WATCH" or p.direction == "NEUTRAL":
            continue  # skip non-active positions

        if p.pnl_pct is None:
            pnl_str = "—"
        elif p.pnl_pct >= 0:
            pnl_str = f"✅ +{p.pnl_pct:.1f}%"
            wins += 1
        else:
            pnl_str = f"❌ {p.pnl_pct:.1f}%"
            losses += 1

        # Check stop-loss breach
        stop_hit = ""
        if p.stop_price and p.current_price:
            if p.direction == "LONG" and p.current_price <= p.stop_price:
                stop_hit = " 🛑 止损触发!"
                stopped += 1
            elif p.direction == "SHORT" and p.current_price >= p.stop_price:
                stop_hit = " 🛑 止损触发!"
                stopped += 1

        price_str = f"${p.current_price:.2f}" if p.current_price else "—"
        size = f" [{p.size_pct}]" if p.size_pct else ""
        lines.append(
            f"  {p.date} {p.direction}{size} <b>{p.ticker}</b> "
            f"入 ${p.entry_price:.2f} → 现 {price_str} = {pnl_str}{stop_hit}"
        )
        lines.append(f"    逻辑: {p.thesis}")

    total = wins + losses
    if total > 0:
        lines.append(f"\n  <b>胜率: {wins}/{total} ({wins/total:.0%})</b>")
        if stopped:
            lines.append(f"  ⚠️ {stopped} 个仓位触发止损")

    return "\n".join(lines)
