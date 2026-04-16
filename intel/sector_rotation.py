"""
F7: Sector rotation quantification.

Ranks SPDR sector ETFs by 20-day momentum to reveal leadership/laggards.
Free via yfinance. Identifies "risk-on" vs "defensive" rotation.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

import yfinance as yf


SECTORS: list[tuple[str, str, str]] = [
    # ticker, name, type
    ("XLK", "Technology", "cyclical"),
    ("XLY", "Consumer Discretionary", "cyclical"),
    ("XLF", "Financials", "cyclical"),
    ("XLI", "Industrials", "cyclical"),
    ("XLB", "Materials", "cyclical"),
    ("XLE", "Energy", "cyclical"),
    ("XLC", "Communication Services", "cyclical"),
    ("XLP", "Consumer Staples", "defensive"),
    ("XLV", "Healthcare", "defensive"),
    ("XLU", "Utilities", "defensive"),
    ("XLRE", "Real Estate", "rate-sensitive"),
]


@dataclass
class SectorPerf:
    ticker: str
    name: str
    sector_type: str
    momentum_20d: float = 0.0
    momentum_5d: float = 0.0
    err: str = ""


def compute_sector_rotation() -> list[SectorPerf]:
    results = []
    tickers = [s[0] for s in SECTORS]
    try:
        hist = yf.download(
            " ".join(tickers), period="2mo", interval="1d",
            progress=False, auto_adjust=False, group_by="ticker",
        )
    except Exception as e:
        print(f"[sector] download failed: {e}", file=sys.stderr)
        return [SectorPerf(t, n, st, err=str(e)) for t, n, st in SECTORS]

    for ticker, name, stype in SECTORS:
        perf = SectorPerf(ticker=ticker, name=name, sector_type=stype)
        try:
            col = hist[ticker]["Close"].dropna()
            if len(col) < 21:
                perf.err = "insufficient data"
            else:
                last = float(col.iloc[-1])
                perf.momentum_20d = (last / float(col.iloc[-21]) - 1) * 100
                if len(col) >= 6:
                    perf.momentum_5d = (last / float(col.iloc[-6]) - 1) * 100
        except Exception as e:
            perf.err = str(e)[:50]
        results.append(perf)

    # Sort by 20d momentum descending
    results.sort(key=lambda x: x.momentum_20d, reverse=True)
    return results


def format_sector_panel(perfs: list[SectorPerf]) -> str:
    lines = ["🔄 <b>板块轮动 (20d 动量排序)</b>"]
    for p in perfs:
        if p.err:
            continue
        arrow = "🟢" if p.momentum_20d >= 0 else "🔴"
        lines.append(
            f"  {arrow} {p.name} ({p.ticker}): {p.momentum_20d:+.1f}% / 5d {p.momentum_5d:+.1f}% [{p.sector_type}]"
        )
    # Detect rotation signal
    cyclical_avg = sum(p.momentum_20d for p in perfs if p.sector_type == "cyclical" and not p.err) / max(1, sum(1 for p in perfs if p.sector_type == "cyclical" and not p.err))
    defensive_avg = sum(p.momentum_20d for p in perfs if p.sector_type == "defensive" and not p.err) / max(1, sum(1 for p in perfs if p.sector_type == "defensive" and not p.err))
    if cyclical_avg > defensive_avg + 2:
        lines.append(f"  💡 Risk-ON: 周期股领先防御股 {cyclical_avg - defensive_avg:+.1f}%")
    elif defensive_avg > cyclical_avg + 2:
        lines.append(f"  💡 Risk-OFF: 防御股领先周期股 {defensive_avg - cyclical_avg:+.1f}%")
    return "\n".join(lines)


def format_sector_for_analyst(perfs: list[SectorPerf]) -> str:
    lines = ["# Sector Rotation (20-day momentum, ranked)"]
    for p in perfs:
        if p.err:
            continue
        lines.append(
            f"- {p.name} ({p.ticker}): {p.momentum_20d:+.2f}% 20d, "
            f"{p.momentum_5d:+.2f}% 5d [{p.sector_type}]"
        )
    return "\n".join(lines)
