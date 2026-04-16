"""
F6: FRED API for macroeconomic stress indicators.

Requires FRED_API_KEY in .env. Gracefully no-ops if key missing.

Key series:
- BAMLH0A0HYM2 — ICE BofA US High Yield OAS (credit stress)
- T10Y2Y — 10Y minus 2Y Treasury spread (recession indicator)
- DFII10 — 10Y TIPS (real yield)
- DCOILWTICO — WTI oil
- VIXCLS — VIX close
- STLFSI4 — St. Louis Financial Stress Index
- WALCL — Fed balance sheet
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import date, timedelta

import requests as _requests


FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

SERIES = {
    "BAMLH0A0HYM2": "高收益债利差 (OAS)",
    "T10Y2Y": "10Y-2Y 利差",
    "DFII10": "10Y TIPS 实际利率",
    "STLFSI4": "金融压力指数",
    "DCOILWTICO": "WTI 原油",
    "UNRATE": "失业率",
    "CPIAUCSL": "CPI (全部商品)",
}


@dataclass
class FredSeries:
    series_id: str
    name: str
    latest_value: float | None = None
    latest_date: str = ""
    change_1m: float | None = None
    err: str = ""

    @property
    def ok(self) -> bool:
        return self.err == "" and self.latest_value is not None


def _fetch_series(series_id: str, api_key: str) -> list[dict]:
    end = date.today().strftime("%Y-%m-%d")
    start = (date.today() - timedelta(days=60)).strftime("%Y-%m-%d")
    try:
        r = _requests.get(
            FRED_BASE,
            params={
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "observation_start": start,
                "observation_end": end,
                "sort_order": "desc",
            },
            timeout=15,
        )
        if r.status_code != 200:
            return []
        return r.json().get("observations", [])
    except Exception as e:
        print(f"[fred] {series_id}: {e}", file=sys.stderr)
        return []


def fetch_fred_indicators() -> list[FredSeries]:
    """Fetch all key FRED series. Returns empty list if no API key."""
    key = os.environ.get("FRED_API_KEY", "")
    if not key:
        return []

    results = []
    for series_id, name in SERIES.items():
        fs = FredSeries(series_id=series_id, name=name)
        obs = _fetch_series(series_id, key)
        # Find latest non-empty value
        latest = None
        prev_month = None
        for o in obs:
            if o.get("value") and o["value"] != ".":
                try:
                    val = float(o["value"])
                    if latest is None:
                        latest = val
                        fs.latest_date = o.get("date", "")
                    else:
                        # Found value ~1 month before
                        prev_month = val
                        break
                except ValueError:
                    continue
        fs.latest_value = latest
        if latest is not None and prev_month is not None and prev_month != 0:
            fs.change_1m = (latest - prev_month) / abs(prev_month) * 100
        results.append(fs)
    return results


def format_fred_panel(series_list: list[FredSeries]) -> str:
    if not series_list:
        return ""
    lines = ["📉 <b>FRED 宏观压力指标</b>"]
    for s in series_list:
        if not s.ok:
            continue
        chg = f" ({s.change_1m:+.1f}% 1m)" if s.change_1m is not None else ""
        lines.append(f"  {s.name}: {s.latest_value:.2f}{chg}")
    return "\n".join(lines)


def format_fred_for_analyst(series_list: list[FredSeries]) -> str:
    if not series_list:
        return "# FRED Indicators: API key not configured"
    lines = ["# FRED Macro Stress Indicators"]
    for s in series_list:
        if not s.ok:
            continue
        chg = f" ({s.change_1m:+.1f}% MoM)" if s.change_1m is not None else ""
        lines.append(
            f"- {s.name} ({s.series_id}): {s.latest_value:.2f} "
            f"as of {s.latest_date}{chg}"
        )
    lines.append("- Interpretation hints: HY OAS > 500bp = credit stress; "
                 "T10Y2Y < 0 = yield curve inverted (recession signal); "
                 "STLFSI4 > 1 = financial stress above historical norm.")
    return "\n".join(lines)
