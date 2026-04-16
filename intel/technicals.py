"""
Technical analysis indicators for watchlist stocks and macro tickers.
All computed from yfinance historical data — no external API needed.

Provides:
- SMA 50/200 (golden/death cross detection)
- RSI 14
- Bollinger Bands (20, 2σ)
- Distance from key levels
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

import yfinance as yf
import numpy as np


@dataclass
class TechnicalSnapshot:
    ticker: str
    name: str
    last: float | None = None
    sma50: float | None = None
    sma200: float | None = None
    sma_signal: str = ""       # "金叉" / "死叉" / "多头排列" / "空头排列"
    rsi14: float | None = None
    rsi_signal: str = ""       # "超买" / "超卖" / "中性"
    bb_upper: float | None = None
    bb_lower: float | None = None
    bb_signal: str = ""        # "触及上轨" / "触及下轨" / "带内"
    pct_from_52w_high: float | None = None
    pct_from_52w_low: float | None = None
    err: str = ""

    @property
    def ok(self) -> bool:
        return self.err == "" and self.last is not None


def _sma(series, window: int):
    return series.rolling(window=window, min_periods=window).mean()


def _rsi(series, period: int = 14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _bollinger(series, window: int = 20, num_std: float = 2.0):
    mid = series.rolling(window=window).mean()
    std = series.rolling(window=window).std()
    return mid + num_std * std, mid - num_std * std


def compute_technicals(tickers: list[tuple[str, str]]) -> list[TechnicalSnapshot]:
    """Compute technical indicators for a list of (ticker, name) pairs."""
    results = []
    for ticker, name in tickers:
        snap = TechnicalSnapshot(ticker=ticker, name=name)
        try:
            hist = yf.download(
                ticker, period="1y", interval="1d",
                progress=False, auto_adjust=False,
            )
            if hist is None or len(hist) < 50:
                snap.err = "insufficient data"
                results.append(snap)
                continue

            close = hist["Close"].squeeze()
            last = float(close.iloc[-1])
            snap.last = last

            # SMA 50/200
            s50 = _sma(close, 50)
            s200 = _sma(close, 200)
            if len(s50.dropna()) > 0:
                snap.sma50 = float(s50.iloc[-1])
            if len(s200.dropna()) > 0:
                snap.sma200 = float(s200.iloc[-1])
            if snap.sma50 and snap.sma200:
                prev_s50 = float(s50.iloc[-2]) if len(s50.dropna()) > 1 else snap.sma50
                prev_s200 = float(s200.iloc[-2]) if len(s200.dropna()) > 1 else snap.sma200
                if prev_s50 <= prev_s200 and snap.sma50 > snap.sma200:
                    snap.sma_signal = "金叉 ⚡"
                elif prev_s50 >= prev_s200 and snap.sma50 < snap.sma200:
                    snap.sma_signal = "死叉 ⚠️"
                elif snap.sma50 > snap.sma200:
                    snap.sma_signal = "多头排列"
                else:
                    snap.sma_signal = "空头排列"

            # RSI 14
            rsi = _rsi(close, 14)
            if len(rsi.dropna()) > 0:
                snap.rsi14 = float(rsi.iloc[-1])
                if snap.rsi14 >= 70:
                    snap.rsi_signal = "超买 🔴"
                elif snap.rsi14 <= 30:
                    snap.rsi_signal = "超卖 🟢"
                else:
                    snap.rsi_signal = "中性"

            # Bollinger Bands
            bb_up, bb_low = _bollinger(close, 20, 2.0)
            if len(bb_up.dropna()) > 0:
                snap.bb_upper = float(bb_up.iloc[-1])
                snap.bb_lower = float(bb_low.iloc[-1])
                if last >= snap.bb_upper * 0.99:
                    snap.bb_signal = "触及上轨"
                elif last <= snap.bb_lower * 1.01:
                    snap.bb_signal = "触及下轨"
                else:
                    snap.bb_signal = "带内"

            # 52-week high/low
            high_52w = float(close.tail(252).max()) if len(close) >= 252 else float(close.max())
            low_52w = float(close.tail(252).min()) if len(close) >= 252 else float(close.min())
            snap.pct_from_52w_high = (last - high_52w) / high_52w * 100
            snap.pct_from_52w_low = (last - low_52w) / low_52w * 100

        except Exception as e:
            snap.err = str(e)[:80]
            print(f"[technicals] {ticker}: {e}", file=sys.stderr)

        results.append(snap)
    return results


def format_technicals_panel(snaps: list[TechnicalSnapshot]) -> str:
    """Format for Telegram display — compact tabular layout."""
    lines = ["📐 <b>技术指标</b>"]
    for s in snaps:
        if not s.ok:
            lines.append(f"• {s.name} ({s.ticker}): —")
            continue
        parts = [f"<b>{s.name}</b> ({s.ticker})"]
        if s.sma50 and s.sma200:
            parts.append(
                f"  SMA: 50d={s.sma50:.1f} / 200d={s.sma200:.1f} → {s.sma_signal}"
            )
        if s.rsi14 is not None:
            parts.append(f"  RSI14: {s.rsi14:.1f} ({s.rsi_signal})")
        if s.bb_upper and s.bb_lower:
            parts.append(
                f"  Bollinger: [{s.bb_lower:.1f} — {s.bb_upper:.1f}] {s.bb_signal}"
            )
        if s.pct_from_52w_high is not None:
            parts.append(
                f"  52w: 距高点 {s.pct_from_52w_high:+.1f}% / 距低点 {s.pct_from_52w_low:+.1f}%"
            )
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


def format_technicals_for_analyst(snaps: list[TechnicalSnapshot]) -> str:
    """Structured text block to feed into Claude analyst user_prompt."""
    lines = ["# Technical Indicators (computed, not opinion)"]
    for s in snaps:
        if not s.ok:
            continue
        lines.append(f"\n## {s.name} ({s.ticker}) — last: ${s.last:.2f}")
        if s.sma50 and s.sma200:
            lines.append(f"- SMA50: {s.sma50:.2f}, SMA200: {s.sma200:.2f} → {s.sma_signal}")
        if s.rsi14 is not None:
            lines.append(f"- RSI14: {s.rsi14:.1f} → {s.rsi_signal}")
        if s.bb_upper and s.bb_lower:
            lines.append(f"- Bollinger Band: [{s.bb_lower:.2f}, {s.bb_upper:.2f}] → {s.bb_signal}")
        if s.pct_from_52w_high is not None:
            lines.append(
                f"- 52-week: {s.pct_from_52w_high:+.1f}% from high, "
                f"{s.pct_from_52w_low:+.1f}% from low"
            )
    return "\n".join(lines)
