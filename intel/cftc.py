"""
CFTC Commitments of Traders (COT) data. Weekly positioning data for
futures markets — shows what institutional/leveraged money is doing.

Source: CFTC publishes CSV every Friday at
https://www.cftc.gov/dea/newcot/deafut.txt (futures only, current week)

Key contracts we track:
- S&P 500 E-mini (ES) — equity positioning
- Gold (GC) — safe haven positioning
- Crude Oil (CL) — energy/geopolitical proxy
- US Treasury 10Y (TY) — rate expectations
- USD Index (DX) — dollar conviction
"""
from __future__ import annotations

import csv
import io
import sys
import urllib.request
from dataclasses import dataclass


COT_URL = "https://www.cftc.gov/dea/newcot/deafut.txt"

# Map CFTC contract names to our labels
TRACKED_CONTRACTS = {
    "E-MINI S&P 500": "S&P 500 期货",
    "GOLD": "黄金期货",
    "CRUDE OIL": "原油期货",
    "10-YEAR": "10Y 国债期货",
    "U.S. DOLLAR INDEX": "美元指数期货",
}


@dataclass
class CotPosition:
    contract: str
    label: str
    date: str
    leveraged_long: int = 0
    leveraged_short: int = 0
    leveraged_net: int = 0
    net_change: int = 0  # week-over-week
    signal: str = ""     # "净多" / "净空" / "翻多" / "翻空"


def fetch_cot_data() -> list[CotPosition]:
    """Fetch and parse latest CFTC COT report."""
    try:
        req = urllib.request.Request(
            COT_URL,
            headers={"User-Agent": "market-intel/1.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[cftc] fetch failed: {e}", file=sys.stderr)
        return []

    results = []
    try:
        reader = csv.DictReader(io.StringIO(raw))
        for row in reader:
            name = (row.get("Market_and_Exchange_Names") or "").upper()
            matched_label = None
            for pattern, label in TRACKED_CONTRACTS.items():
                if pattern in name:
                    matched_label = label
                    break
            if not matched_label:
                continue

            try:
                lev_long = int(row.get("Lev_Money_Positions_Long_All", 0) or 0)
                lev_short = int(row.get("Lev_Money_Positions_Short_All", 0) or 0)
                lev_net = lev_long - lev_short
                # Change vs prior week
                prev_long = int(row.get("Change_in_Lev_Money_Long_All", 0) or 0)
                prev_short = int(row.get("Change_in_Lev_Money_Short_All", 0) or 0)
                net_change = prev_long - prev_short
            except (ValueError, TypeError):
                lev_long = lev_short = lev_net = net_change = 0

            signal = "净多" if lev_net > 0 else "净空"
            if net_change != 0:
                if lev_net > 0 and net_change > 0:
                    signal = "净多 ↑ 加仓"
                elif lev_net > 0 and net_change < 0:
                    signal = "净多 ↓ 减仓"
                elif lev_net < 0 and net_change < 0:
                    signal = "净空 ↑ 加仓"
                elif lev_net < 0 and net_change > 0:
                    signal = "净空 ↓ 减仓"

            results.append(CotPosition(
                contract=name.split(" - ")[0].strip()[:40],
                label=matched_label,
                date=row.get("As_of_Date_In_Form_YYMMDD", ""),
                leveraged_long=lev_long,
                leveraged_short=lev_short,
                leveraged_net=lev_net,
                net_change=net_change,
                signal=signal,
            ))
    except Exception as e:
        print(f"[cftc] parse error: {e}", file=sys.stderr)

    return results


def format_cot_panel(positions: list[CotPosition]) -> str:
    if not positions:
        return "📊 <b>CFTC 持仓</b>\n数据暂不可用"
    lines = ["📊 <b>CFTC 机构持仓 (周度)</b>"]
    for p in positions:
        lines.append(
            f"  {p.label}: 净 {p.leveraged_net:+,} ({p.signal})"
            f" [周变化 {p.net_change:+,}]"
        )
    return "\n".join(lines)


def format_cot_for_analyst(positions: list[CotPosition]) -> str:
    if not positions:
        return "# CFTC COT: data unavailable this week"
    lines = ["# CFTC Commitments of Traders (leveraged money, weekly)"]
    for p in positions:
        lines.append(
            f"- {p.label} ({p.contract}): net {p.leveraged_net:+,} "
            f"({p.signal}), week change {p.net_change:+,}"
        )
    lines.append(
        "- Interpretation: large net-long = crowded bullish (contrarian "
        "bearish risk); large net-short = crowded bearish (short-squeeze risk)."
    )
    return "\n".join(lines)
