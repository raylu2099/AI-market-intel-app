"""
Q3: Earnings tracking via Financial Datasets API.

Provides:
- Last 4 quarters: actual EPS vs consensus estimate + beat/miss
- Revenue trend (QoQ and YoY)
- Forward consensus EPS (next 1-2 fiscal years)
- Recent insider trades (net buy/sell signal)

This is the module that bridges "news-driven opinion" to "data-driven research".
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field

import requests as _requests

from .config import Config

API_BASE = "https://api.financialdatasets.ai"


def _api_get(cfg: Config, path: str, params: dict) -> dict:
    key = os.environ.get("FINANCIAL_DATASETS_API_KEY", "")
    if not key:
        return {}
    url = f"{API_BASE}/{path}"
    try:
        resp = _requests.get(
            url,
            params=params,
            headers={"X-API-Key": key},
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"[earnings] API {resp.status_code} for {path}", file=sys.stderr)
            return {}
        return resp.json()
    except Exception as e:
        print(f"[earnings] API error {path}: {e}", file=sys.stderr)
        return {}


@dataclass
class QuarterlyEarnings:
    fiscal_period: str
    revenue: float  # in billions
    eps_actual: float
    eps_estimate: float | None = None
    surprise: str = ""  # "BEAT" / "MISS" / ""
    revenue_yoy_pct: float | None = None


@dataclass
class EarningsProfile:
    ticker: str
    name: str
    quarters: list[QuarterlyEarnings] = field(default_factory=list)
    fwd_eps_1y: float | None = None
    fwd_eps_2y: float | None = None
    fwd_revenue_1y: float | None = None  # in billions
    beat_rate: float | None = None  # last 4Q beat rate (0.0 - 1.0)
    net_insider_shares: float = 0.0  # positive = net buying
    insider_trades_30d: int = 0
    err: str = ""


def fetch_earnings_profile(cfg: Config, ticker: str, name: str) -> EarningsProfile:
    profile = EarningsProfile(ticker=ticker, name=name)

    # 1. Last 4 quarters income statements
    data = _api_get(cfg, "financials/income-statements", {
        "ticker": ticker, "period": "quarterly", "limit": 8,
    })
    stmts = data.get("income_statements") or []
    quarters: list[QuarterlyEarnings] = []
    for s in stmts[:4]:
        rev = s.get("revenue") or 0
        eps = s.get("earnings_per_share_diluted") or s.get("earnings_per_share") or 0
        quarters.append(QuarterlyEarnings(
            fiscal_period=s.get("fiscal_period", ""),
            revenue=rev / 1e9,
            eps_actual=eps,
        ))

    # Compute YoY revenue (compare Q vs same Q last year)
    if len(stmts) >= 8:
        for i, q in enumerate(quarters[:4]):
            yoy_q = stmts[i + 4] if i + 4 < len(stmts) else None
            if yoy_q and yoy_q.get("revenue"):
                q.revenue_yoy_pct = (
                    (q.revenue * 1e9 - yoy_q["revenue"]) / yoy_q["revenue"] * 100
                )

    # 2. Earnings surprise (beat/miss)
    earnings_data = _api_get(cfg, "earnings", {"ticker": ticker})
    earnings = earnings_data.get("earnings") or {}
    qe = earnings.get("quarterly") or {}
    if qe:
        est = qe.get("estimated_earnings_per_share")
        surprise = qe.get("eps_surprise", "")
        if quarters:
            quarters[0].eps_estimate = est
            quarters[0].surprise = surprise

    # Calculate beat rate from available data
    beats = sum(1 for q in quarters if q.surprise == "BEAT")
    if quarters:
        profile.beat_rate = beats / len(quarters)

    profile.quarters = quarters

    # 3. Forward analyst estimates
    est_data = _api_get(cfg, "analyst-estimates", {"ticker": ticker, "limit": 2})
    estimates = est_data.get("analyst_estimates") or []
    if len(estimates) >= 1:
        profile.fwd_eps_1y = estimates[0].get("earnings_per_share")
        rev = estimates[0].get("revenue")
        if rev:
            profile.fwd_revenue_1y = rev / 1e9
    if len(estimates) >= 2:
        profile.fwd_eps_2y = estimates[1].get("earnings_per_share")

    # 4. Insider trades (last 30 days)
    insider_data = _api_get(cfg, "insider-trades", {"ticker": ticker, "limit": 20})
    trades = insider_data.get("insider_trades") or []
    net_shares = 0.0
    count = 0
    for t in trades:
        shares = t.get("transaction_shares") or 0
        ttype = (t.get("transaction_type") or "").lower()
        if "purchase" in ttype or "buy" in ttype:
            net_shares += shares
        elif "sale" in ttype or "sell" in ttype:
            net_shares -= shares
        count += 1
    profile.net_insider_shares = net_shares
    profile.insider_trades_30d = count

    return profile


def fetch_all_earnings(cfg: Config) -> list[EarningsProfile]:
    return [fetch_earnings_profile(cfg, t, n) for t, n in cfg.watchlist]


def format_earnings_panel(profiles: list[EarningsProfile]) -> str:
    lines = ["📈 <b>盈利追踪</b>"]
    for p in profiles:
        if p.err:
            lines.append(f"\n<b>{p.name}</b> ({p.ticker}): {p.err}")
            continue

        parts = [f"\n<b>{p.name}</b> ({p.ticker})"]

        # Latest quarter
        if p.quarters:
            q = p.quarters[0]
            est_str = f" vs 预期 ${q.eps_estimate:.2f}" if q.eps_estimate else ""
            surprise_emoji = "✅" if q.surprise == "BEAT" else ("❌" if q.surprise == "MISS" else "")
            yoy = f" (YoY {q.revenue_yoy_pct:+.0f}%)" if q.revenue_yoy_pct is not None else ""
            parts.append(
                f"  最新 {q.fiscal_period}: EPS ${q.eps_actual:.2f}{est_str} {surprise_emoji}"
            )
            parts.append(f"  营收 ${q.revenue:.1f}B{yoy}")

        # Beat rate
        if p.beat_rate is not None and p.quarters:
            parts.append(f"  近 {len(p.quarters)}Q beat 率: {p.beat_rate:.0%}")

        # Forward estimates
        if p.fwd_eps_1y:
            fwd = f"  前瞻 EPS: 1Y ${p.fwd_eps_1y:.2f}"
            if p.fwd_eps_2y:
                fwd += f" → 2Y ${p.fwd_eps_2y:.2f}"
            parts.append(fwd)
        if p.fwd_revenue_1y:
            parts.append(f"  前瞻营收: 1Y ${p.fwd_revenue_1y:.0f}B")

        # Insider signal
        if p.insider_trades_30d > 0:
            direction = "净买入" if p.net_insider_shares > 0 else "净卖出"
            parts.append(
                f"  内部人: {p.insider_trades_30d} 笔交易, "
                f"{direction} {abs(p.net_insider_shares):,.0f} 股"
            )

        lines.append("\n".join(parts))
    return "\n\n".join(lines)


def format_earnings_for_analyst(profiles: list[EarningsProfile]) -> str:
    """Structured text for Claude analyst user_prompt."""
    lines = ["# Earnings & Fundamentals (Financial Datasets API)"]
    for p in profiles:
        if p.err:
            continue
        lines.append(f"\n## {p.name} ({p.ticker})")

        if p.quarters:
            q = p.quarters[0]
            lines.append(f"- Latest quarter ({q.fiscal_period}):")
            lines.append(f"  EPS actual: ${q.eps_actual:.2f}")
            if q.eps_estimate:
                lines.append(f"  EPS estimate: ${q.eps_estimate:.2f} → {q.surprise}")
            lines.append(f"  Revenue: ${q.revenue:.1f}B")
            if q.revenue_yoy_pct is not None:
                lines.append(f"  Revenue YoY: {q.revenue_yoy_pct:+.1f}%")

        # EPS trend (last 4Q)
        if len(p.quarters) >= 2:
            trend = " → ".join(
                f"${q.eps_actual:.2f}" for q in reversed(p.quarters)
            )
            lines.append(f"- EPS trend (oldest→newest): {trend}")

        if p.beat_rate is not None:
            lines.append(f"- Beat rate (last {len(p.quarters)}Q): {p.beat_rate:.0%}")

        if p.fwd_eps_1y:
            lines.append(f"- Forward EPS consensus: 1Y ${p.fwd_eps_1y:.2f}")
            if p.fwd_eps_2y:
                lines.append(f"  2Y ${p.fwd_eps_2y:.2f} ({(p.fwd_eps_2y/p.fwd_eps_1y-1)*100:+.0f}% growth)")

        if p.fwd_revenue_1y:
            lines.append(f"- Forward revenue consensus: 1Y ${p.fwd_revenue_1y:.0f}B")

        if p.insider_trades_30d > 0:
            direction = "NET BUY" if p.net_insider_shares > 0 else "NET SELL"
            lines.append(
                f"- Insider activity (30d): {p.insider_trades_30d} trades, "
                f"{direction} {abs(p.net_insider_shares):,.0f} shares"
            )

    return "\n".join(lines)
