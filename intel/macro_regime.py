"""
Macro regime identification — systematic, not vibes.

Uses actual price data to classify the current environment into one of
four quadrants (Goldman GOAL-style):

              Growth ↑
    ┌──────────────┬──────────────┐
    │  GOLDILOCKS  │  REFLATION   │
    │  SPY↑ DXY↓   │  SPY↑ DXY↑   │
    │  Bonds↑      │  Commod↑     │
    ├──────────────┼──────────────┤
    │  DEFLATION   │ STAGFLATION  │
    │  SPY↓ DXY↓   │  SPY↓ DXY↑   │
    │  Gold↑       │  Oil↑ Bonds↓ │
    └──────────────┴──────────────┘
              Growth ↓

Implementation: use 20-day momentum of SPY (growth proxy) and
^TNX/DXY (inflation/tightening proxy) to classify.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

import yfinance as yf
import numpy as np


@dataclass
class RegimeSnapshot:
    regime: str          # "GOLDILOCKS" | "REFLATION" | "STAGFLATION" | "DEFLATION"
    growth_momentum: float    # 20d return of SPY
    inflation_momentum: float  # 20d return of DXY (or ^TNX)
    vix: float | None = None
    vix_signal: str = ""     # "低波" / "正常" / "恐慌"
    yield_curve_2s10s: float | None = None  # 10Y - 3M spread
    credit_spread: float | None = None  # HYG/LQD ratio momentum
    detail: str = ""
    err: str = ""


def compute_regime() -> RegimeSnapshot:
    snap = RegimeSnapshot(regime="UNKNOWN", growth_momentum=0, inflation_momentum=0)
    try:
        tickers = ["SPY", "DX-Y.NYB", "^VIX", "^TNX", "^IRX", "HYG", "LQD"]
        hist = yf.download(
            " ".join(tickers), period="2mo", interval="1d",
            progress=False, auto_adjust=False, group_by="ticker",
        )
        if hist is None or hist.empty:
            snap.err = "download failed"
            return snap

        def momentum(ticker, days=20):
            try:
                col = hist[ticker]["Close"].dropna()
                if len(col) < days + 1:
                    return 0.0
                return float((col.iloc[-1] / col.iloc[-days - 1] - 1) * 100)
            except Exception:
                return 0.0

        spy_mom = momentum("SPY", 20)
        dxy_mom = momentum("DX-Y.NYB", 20)

        snap.growth_momentum = spy_mom
        snap.inflation_momentum = dxy_mom

        # Regime classification
        if spy_mom > 0 and dxy_mom <= 0:
            snap.regime = "GOLDILOCKS"
            snap.detail = "增长 + 宽松：股票友好环境，成长股跑赢"
        elif spy_mom > 0 and dxy_mom > 0:
            snap.regime = "REFLATION"
            snap.detail = "增长 + 通胀：大宗商品 + 周期股受益"
        elif spy_mom <= 0 and dxy_mom > 0:
            snap.regime = "STAGFLATION"
            snap.detail = "衰退 + 通胀：最危险 regime，现金 + 黄金避险"
        else:
            snap.regime = "DEFLATION"
            snap.detail = "衰退 + 通缩：长债受益，风险资产承压"

        # VIX
        try:
            vix_col = hist["^VIX"]["Close"].dropna()
            if len(vix_col) > 0:
                snap.vix = float(vix_col.iloc[-1])
                if snap.vix < 15:
                    snap.vix_signal = "低波"
                elif snap.vix < 25:
                    snap.vix_signal = "正常"
                elif snap.vix < 35:
                    snap.vix_signal = "恐慌"
                else:
                    snap.vix_signal = "极度恐慌 🚨"
        except Exception:
            pass

        # 2s10s spread (10Y - 3M as proxy; proper 2Y would need ^FVX)
        try:
            tnx = float(hist["^TNX"]["Close"].dropna().iloc[-1])
            irx = float(hist["^IRX"]["Close"].dropna().iloc[-1])
            snap.yield_curve_2s10s = tnx - irx  # 10Y - 3M
        except Exception:
            pass

        # Credit spread proxy: HYG/LQD ratio momentum
        # Falling ratio = widening spreads = risk-off signal
        try:
            hyg = hist["HYG"]["Close"].dropna()
            lqd = hist["LQD"]["Close"].dropna()
            if len(hyg) > 20 and len(lqd) > 20:
                ratio = hyg / lqd
                ratio_now = float(ratio.iloc[-1])
                ratio_20d = float(ratio.iloc[-21])
                snap.credit_spread = (ratio_now / ratio_20d - 1) * 100
        except Exception:
            pass

    except Exception as e:
        snap.err = str(e)[:80]
        print(f"[regime] error: {e}", file=sys.stderr)

    return snap


def format_regime_panel(snap: RegimeSnapshot) -> str:
    if snap.err:
        return f"🌡️ <b>宏观 Regime</b>: 计算失败 ({snap.err})"
    lines = [f"🌡️ <b>宏观 Regime: {snap.regime}</b>"]
    lines.append(f"  {snap.detail}")
    lines.append(
        f"  SPY 20d: {snap.growth_momentum:+.1f}% | "
        f"DXY 20d: {snap.inflation_momentum:+.1f}%"
    )
    if snap.vix is not None:
        lines.append(f"  VIX: {snap.vix:.1f} ({snap.vix_signal})")
    if snap.yield_curve_2s10s is not None:
        inv = " ⚠️ 倒挂" if snap.yield_curve_2s10s < 0 else ""
        lines.append(f"  收益率曲线 (10Y-3M): {snap.yield_curve_2s10s:+.2f}%{inv}")
    if snap.credit_spread is not None:
        stress = " ⚠️ 信用压力" if snap.credit_spread < -0.5 else ""
        lines.append(f"  信用利差 (HYG/LQD 20d): {snap.credit_spread:+.2f}%{stress}")
    return "\n".join(lines)


def format_regime_for_analyst(snap: RegimeSnapshot) -> str:
    """Structured text for Claude analyst user_prompt."""
    if snap.err:
        return f"# Macro Regime: UNKNOWN (error: {snap.err})"
    lines = [
        f"# Macro Regime: {snap.regime}",
        f"- Interpretation: {snap.detail}",
        f"- SPY 20-day momentum: {snap.growth_momentum:+.2f}%",
        f"- DXY 20-day momentum: {snap.inflation_momentum:+.2f}%",
    ]
    if snap.vix is not None:
        lines.append(f"- VIX: {snap.vix:.1f} ({snap.vix_signal})")
    if snap.yield_curve_2s10s is not None:
        inv = " (INVERTED)" if snap.yield_curve_2s10s < 0 else ""
        lines.append(f"- Yield curve (10Y-3M spread): {snap.yield_curve_2s10s:+.2f}%{inv}")
    if snap.credit_spread is not None:
        stress = "(credit stress)" if snap.credit_spread < -0.5 else "(stable)"
        lines.append(f"- Credit spread proxy (HYG/LQD 20d): {snap.credit_spread:+.2f}% {stress}")
    lines.append(
        f"- POSITION CHECK: Your position theses MUST be consistent with "
        f"the {snap.regime} regime. If proposing a contrarian bet against "
        f"the regime, explicitly flag and justify."
    )
    return "\n".join(lines)
