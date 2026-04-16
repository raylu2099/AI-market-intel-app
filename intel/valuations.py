"""
Valuation snapshot for watchlist stocks — P/E, forward P/E, P/S, PEG,
market cap, analyst price targets. From yfinance .info (free).

Falls back to Financial Datasets API if FINANCIAL_DATASETS_API_KEY is set.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from dataclasses import dataclass
from typing import Any

import yfinance as yf

from .config import Config


@dataclass
class ValuationSnapshot:
    ticker: str
    name: str
    trailing_pe: float | None = None
    forward_pe: float | None = None
    ps_ratio: float | None = None
    peg_ratio: float | None = None
    market_cap: float | None = None  # in billions
    target_mean: float | None = None
    target_high: float | None = None
    target_low: float | None = None
    num_analysts: int | None = None
    err: str = ""

    @property
    def ok(self) -> bool:
        return self.err == "" and self.trailing_pe is not None


def _safe_get(info: dict, key: str) -> float | None:
    v = info.get(key)
    if v is None or v == "Infinity" or (isinstance(v, float) and v != v):
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def fetch_valuations(tickers: list[tuple[str, str]]) -> list[ValuationSnapshot]:
    results = []
    for ticker, name in tickers:
        snap = ValuationSnapshot(ticker=ticker, name=name)
        try:
            info = yf.Ticker(ticker).info or {}
            snap.trailing_pe = _safe_get(info, "trailingPE")
            snap.forward_pe = _safe_get(info, "forwardPE")
            snap.ps_ratio = _safe_get(info, "priceToSalesTrailing12Months")
            snap.peg_ratio = _safe_get(info, "pegRatio")
            mc = _safe_get(info, "marketCap")
            if mc:
                snap.market_cap = mc / 1e9
            snap.target_mean = _safe_get(info, "targetMeanPrice")
            snap.target_high = _safe_get(info, "targetHighPrice")
            snap.target_low = _safe_get(info, "targetLowPrice")
            na = info.get("numberOfAnalystOpinions")
            if na is not None:
                snap.num_analysts = int(na)
        except Exception as e:
            snap.err = str(e)[:80]
            print(f"[valuations] {ticker}: {e}", file=sys.stderr)
        results.append(snap)
    return results


def format_valuations_panel(snaps: list[ValuationSnapshot]) -> str:
    lines = ["💎 <b>估值快照</b>"]
    for s in snaps:
        if not s.ok:
            lines.append(f"• {s.name} ({s.ticker}): —")
            continue
        parts = [f"<b>{s.name}</b> ({s.ticker})"]
        pe_str = f"P/E: {s.trailing_pe:.1f}" if s.trailing_pe else "P/E: —"
        fpe_str = f"fwd P/E: {s.forward_pe:.1f}" if s.forward_pe else ""
        ps_str = f"P/S: {s.ps_ratio:.1f}" if s.ps_ratio else ""
        peg_str = f"PEG: {s.peg_ratio:.2f}" if s.peg_ratio else ""
        metrics = " | ".join(x for x in [pe_str, fpe_str, ps_str, peg_str] if x)
        parts.append(f"  {metrics}")
        if s.market_cap:
            parts.append(f"  市值: ${s.market_cap:.0f}B")
        if s.target_mean:
            target = f"  目标价: ${s.target_mean:.0f}"
            if s.target_low and s.target_high:
                target += f" (${s.target_low:.0f}–${s.target_high:.0f})"
            if s.num_analysts:
                target += f" [{s.num_analysts} 位分析师]"
            parts.append(target)
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


def format_valuations_for_analyst(snaps: list[ValuationSnapshot]) -> str:
    """Structured text for Claude analyst user_prompt."""
    lines = ["# Valuation Snapshot (from yfinance)"]
    for s in snaps:
        if not s.ok:
            continue
        lines.append(f"\n## {s.name} ({s.ticker})")
        if s.trailing_pe:
            lines.append(f"- Trailing P/E: {s.trailing_pe:.1f}")
        if s.forward_pe:
            lines.append(f"- Forward P/E: {s.forward_pe:.1f}")
        if s.ps_ratio:
            lines.append(f"- P/S: {s.ps_ratio:.1f}")
        if s.peg_ratio:
            lines.append(f"- PEG: {s.peg_ratio:.2f}")
        if s.market_cap:
            lines.append(f"- Market cap: ${s.market_cap:.0f}B")
        if s.target_mean:
            lines.append(
                f"- Analyst target: ${s.target_mean:.0f} "
                f"(range ${s.target_low:.0f}–${s.target_high:.0f}, "
                f"{s.num_analysts} analysts)"
                if s.target_low and s.target_high and s.num_analysts
                else f"- Analyst target: ${s.target_mean:.0f}"
            )
    return "\n".join(lines)
