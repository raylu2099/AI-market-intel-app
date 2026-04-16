"""
P6: Cost tracking. Accumulates Perplexity costs per run into a daily
JSON ledger. Weekly review reads this to produce a cost summary.
"""
from __future__ import annotations

import json
import re
import sys
import threading
from pathlib import Path

from .config import Config
from .timeutil import today_str


_DAILY_COSTS: dict[str, float] = {}
_LOCK = threading.Lock()


def record_cost(component: str, amount: float) -> None:
    """Thread-safe cost accumulation (S4)."""
    with _LOCK:
        _DAILY_COSTS[component] = _DAILY_COSTS.get(component, 0) + amount


def get_session_costs() -> dict[str, float]:
    with _LOCK:
        return dict(_DAILY_COSTS)


def save_daily_costs(cfg: Config, slot: str) -> None:
    """Append costs to daily ledger, thread-safe snapshot+clear (S4)."""
    with _LOCK:
        if not _DAILY_COSTS:
            return
        snapshot = dict(_DAILY_COSTS)
        _DAILY_COSTS.clear()
    date_str = today_str(cfg.market_tz)
    ledger_dir = cfg.data_dir / "costs"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    path = ledger_dir / f"{date_str}.jsonl"
    entry = {"slot": slot, "costs": snapshot}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_weekly_costs(cfg: Config, days: int = 7) -> dict[str, float]:
    """Sum costs from the last N days."""
    from .timeutil import days_back
    totals: dict[str, float] = {}
    ledger_dir = cfg.data_dir / "costs"
    if not ledger_dir.exists():
        return totals
    for date_str in days_back(cfg.market_tz, days):
        path = ledger_dir / f"{date_str}.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                for k, v in entry.get("costs", {}).items():
                    totals[k] = totals.get(k, 0) + v
            except Exception:
                continue
    return totals


def format_weekly_cost_summary(cfg: Config) -> str:
    costs = load_weekly_costs(cfg, 7)
    if not costs:
        return "💰 <b>本周 API 成本</b>\n无记录"
    total = sum(costs.values())
    lines = ["💰 <b>本周 API 成本</b>"]
    for k, v in sorted(costs.items()):
        lines.append(f"  • {k}: ${v:.4f}")
    lines.append(f"  <b>合计: ${total:.4f}</b>")
    return "\n".join(lines)
