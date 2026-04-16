"""
Breaking news watchdog. Runs every 15 minutes via cron.

Does a single cheap Perplexity sonar call checking for market-moving events
in the last 15 minutes. If nothing, exits silently. If something trips the
threshold, sends an alert to Telegram.

To avoid spam: maintains a simple "last_alert.json" file to suppress duplicate
alerts within a cooldown window.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

from ..config import Config
from ..search import PPLX_ENDPOINT
from ..telegram import send_message
from ..timeutil import now_utc
from .base import SlotResult


SLOT_NAME = "watchdog"
CATEGORY = "watchdog"
COOLDOWN_MINUTES = 60
ALERT_KEYWORDS = [
    "tariff", "Fed emergency", "rate cut", "rate hike", "invasion",
    "Taiwan strait", "Taiwan military", "crash", "circuit breaker",
    "sanctions", "default", "bank failure", "nuclear",
    "assassination", "coup", "martial law", "blockade",
]
ALERT_FILE = "data/watchdog_last_alert.json"


def _check_breaking(cfg: Config) -> str | None:
    """Returns alert text if breaking news found, None otherwise."""
    kw_str = ", ".join(ALERT_KEYWORDS[:10])
    prompt = (
        f"In the last 30 minutes, has any major market-moving event occurred "
        f"globally? Focus on: sudden tariff announcements, Fed emergency actions, "
        f"military escalation (Taiwan, Hormuz, etc.), major bank or sovereign "
        f"defaults, assassination, or market circuit breakers.\n\n"
        f"If YES: reply with a ONE SENTENCE description in Chinese "
        f"(Simplified) of what happened, with source in brackets.\n"
        f"If NO: reply with exactly the word 'NONE' and nothing else."
    )
    body = {
        "model": cfg.pplx_model_search,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 150,
        "temperature": 0.1,
        "search_recency_filter": "hour",
        "web_search_options": {"search_context_size": "low"},
    }
    req = urllib.request.Request(
        PPLX_ENDPOINT,
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {cfg.perplexity_api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        cost = data.get("usage", {}).get("cost", {}).get("total_cost", 0)
        if cost:
            print(f"[cost] watchdog: ${cost:.5f}", file=sys.stderr)
        content = (
            data.get("choices", [{}])[0]
            .get("message", {}).get("content", "")
        ).strip()
        if not content or content.upper().startswith("NONE"):
            return None
        return content
    except Exception as e:
        print(f"[watchdog] check failed: {e}", file=sys.stderr)
        return None


def _in_cooldown(cfg: Config) -> bool:
    path = cfg.data_dir / "watchdog_last_alert.json"
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text())
        last = data.get("timestamp", 0)
        return (time.time() - last) < COOLDOWN_MINUTES * 60
    except Exception:
        return False


def _record_alert(cfg: Config, text: str) -> None:
    path = cfg.data_dir / "watchdog_last_alert.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "timestamp": time.time(),
        "text": text,
        "utc": now_utc().isoformat(),
    }))


def run(cfg: Config) -> SlotResult:
    if _in_cooldown(cfg):
        return SlotResult(
            slot=SLOT_NAME, category=CATEGORY,
            date_str=now_utc().strftime("%Y-%m-%d"),
            articles=[], messages=[],
        )

    alert_text = _check_breaking(cfg)
    if alert_text is None:
        return SlotResult(
            slot=SLOT_NAME, category=CATEGORY,
            date_str=now_utc().strftime("%Y-%m-%d"),
            articles=[], messages=[],
        )

    msg = f"🚨 <b>突发事件</b>\n\n{alert_text}"
    _record_alert(cfg, alert_text)

    return SlotResult(
        slot=SLOT_NAME, category=CATEGORY,
        date_str=now_utc().strftime("%Y-%m-%d"),
        articles=[], messages=[msg],
    )
