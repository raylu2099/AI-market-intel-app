"""
Tier 2: Sentiment & positioning indicators.

- Short interest (yfinance .info) — per-stock crowding signal
- VIX term structure (^VIX vs ^VIX3M) — fear now vs fear later
- Put/call proxy (SPY options volume) — directional sentiment
- Insider net activity (from earnings.py, reused here for display)

These are classic contrarian indicators: extreme readings often precede
reversals. Goldman/Bridgewater use these routinely.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

import yfinance as yf


@dataclass
class ShortInterest:
    ticker: str
    name: str
    short_pct_float: float | None = None  # e.g. 3.5 = 3.5%
    short_ratio: float | None = None       # days to cover
    signal: str = ""                        # "高做空" / "正常" / "低做空"


@dataclass
class VixTermStructure:
    vix_spot: float | None = None
    vix_3m: float | None = None
    structure: str = ""    # "contango" / "backwardation" / "flat"
    spread: float | None = None  # vix_3m - vix_spot
    signal: str = ""


@dataclass
class PutCallRatio:
    ratio: float | None = None  # puts / calls volume
    signal: str = ""  # "偏空" / "中性" / "偏多"


@dataclass
class SentimentSnapshot:
    shorts: list[ShortInterest]
    vix_term: VixTermStructure
    put_call: PutCallRatio


def fetch_short_interest(tickers: list[tuple[str, str]]) -> list[ShortInterest]:
    results = []
    for ticker, name in tickers:
        si = ShortInterest(ticker=ticker, name=name)
        try:
            info = yf.Ticker(ticker).info or {}
            sf = info.get("shortPercentOfFloat")
            sr = info.get("shortRatio")
            if sf is not None:
                si.short_pct_float = float(sf) * 100 if sf < 1 else float(sf)
            if sr is not None:
                si.short_ratio = float(sr)
            if si.short_pct_float is not None:
                if si.short_pct_float > 10:
                    si.signal = "高做空 ⚠️"
                elif si.short_pct_float > 5:
                    si.signal = "偏高"
                else:
                    si.signal = "正常"
        except Exception as e:
            print(f"[sentiment] short interest {ticker}: {e}", file=sys.stderr)
        results.append(si)
    return results


def fetch_vix_term_structure() -> VixTermStructure:
    vts = VixTermStructure()
    try:
        vix = yf.Ticker("^VIX").fast_info
        vix3m = yf.Ticker("^VIX3M").fast_info
        spot = getattr(vix, "last_price", None)
        v3m = getattr(vix3m, "last_price", None)
        if spot and v3m:
            vts.vix_spot = float(spot)
            vts.vix_3m = float(v3m)
            vts.spread = vts.vix_3m - vts.vix_spot
            if vts.spread > 1.0:
                vts.structure = "contango"
                vts.signal = "正常（远月高于近月）"
            elif vts.spread < -1.0:
                vts.structure = "backwardation"
                vts.signal = "恐慌信号 ⚠️（近月高于远月 = 当前恐慌）"
            else:
                vts.structure = "flat"
                vts.signal = "平坦"
    except Exception as e:
        print(f"[sentiment] VIX term: {e}", file=sys.stderr)
    return vts


def fetch_put_call_ratio() -> PutCallRatio:
    """Estimate equity put/call from SPY options volume."""
    pcr = PutCallRatio()
    try:
        spy = yf.Ticker("SPY")
        dates = spy.options
        if not dates:
            return pcr
        # Use nearest expiry
        chain = spy.option_chain(dates[0])
        total_call_vol = chain.calls["volume"].sum()
        total_put_vol = chain.puts["volume"].sum()
        if total_call_vol > 0:
            pcr.ratio = float(total_put_vol / total_call_vol)
            if pcr.ratio > 1.2:
                pcr.signal = "偏空（put 多于 call）"
            elif pcr.ratio < 0.7:
                pcr.signal = "偏多（call 多于 put）— 可能是反向信号"
            else:
                pcr.signal = "中性"
    except Exception as e:
        print(f"[sentiment] put/call: {e}", file=sys.stderr)
    return pcr


def fetch_sentiment(tickers: list[tuple[str, str]]) -> SentimentSnapshot:
    return SentimentSnapshot(
        shorts=fetch_short_interest(tickers),
        vix_term=fetch_vix_term_structure(),
        put_call=fetch_put_call_ratio(),
    )


def format_sentiment_panel(snap: SentimentSnapshot) -> str:
    lines = ["🧭 <b>情绪 & 持仓</b>"]

    # VIX term structure
    vt = snap.vix_term
    if vt.vix_spot and vt.vix_3m:
        lines.append(
            f"  VIX 期限结构: {vt.vix_spot:.1f} (现) vs {vt.vix_3m:.1f} (3M)"
            f" → {vt.structure} ({vt.signal})"
        )

    # Put/Call
    pc = snap.put_call
    if pc.ratio is not None:
        lines.append(f"  SPY Put/Call: {pc.ratio:.2f} ({pc.signal})")

    # Short interest
    for si in snap.shorts:
        if si.short_pct_float is not None:
            days = f", {si.short_ratio:.1f}天平仓" if si.short_ratio else ""
            lines.append(
                f"  {si.name} 做空: {si.short_pct_float:.1f}% float{days} ({si.signal})"
            )

    return "\n".join(lines)


def format_sentiment_for_analyst(snap: SentimentSnapshot) -> str:
    lines = ["# Sentiment & Positioning Indicators"]

    vt = snap.vix_term
    if vt.vix_spot and vt.vix_3m:
        lines.append(
            f"- VIX term structure: spot {vt.vix_spot:.1f} vs 3M {vt.vix_3m:.1f} "
            f"→ {vt.structure} (spread {vt.spread:+.1f}). "
            f"Backwardation = immediate fear; contango = complacency."
        )

    pc = snap.put_call
    if pc.ratio is not None:
        lines.append(
            f"- SPY equity put/call ratio: {pc.ratio:.2f}. "
            f">1.2 = bearish sentiment (contrarian bullish); "
            f"<0.7 = bullish sentiment (contrarian bearish)."
        )

    crowded = []
    for si in snap.shorts:
        if si.short_pct_float and si.short_pct_float > 5:
            crowded.append(f"{si.name} ({si.ticker}): {si.short_pct_float:.1f}% short")
    if crowded:
        lines.append(f"- Elevated short interest (>5% float): {'; '.join(crowded)}")
        lines.append("  High short interest = potential squeeze if catalyst positive.")

    return "\n".join(lines)
