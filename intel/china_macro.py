"""
Q9: China high-frequency macro data. Fetches from public sources:
- PMI (NBS/Caixin) — via Perplexity search for latest reading
- PBOC operations (MLF/LPR/RRR) — via Perplexity
- Property transaction volumes — via Perplexity
- Export/import data — via Perplexity

All searches use sonar (cheapest), return structured Chinese text.
Data is cached per-day to avoid redundant API calls.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

from .config import Config
from .cost_tracker import record_cost
from .search import PPLX_ENDPOINT
from .timeutil import today_str, BEIJING


def _pplx_query(cfg: Config, prompt: str, max_tokens: int = 400) -> str:
    body = json.dumps({
        "model": cfg.pplx_model_search,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.1,
        "search_recency_filter": "month",
        "web_search_options": {"search_context_size": "low"},
    }).encode()
    req = urllib.request.Request(
        PPLX_ENDPOINT,
        data=body,
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
            record_cost("perplexity_china_macro", cost)
        return (
            data.get("choices", [{}])[0]
            .get("message", {}).get("content", "")
        ).strip()
    except Exception as e:
        print(f"[china_macro] query failed: {e}", file=sys.stderr)
        return ""


def _cache_path(cfg: Config) -> Path:
    return cfg.data_dir / "cache" / f"china_macro_{today_str(BEIJING)}.json"


def _load_cache(cfg: Config) -> dict | None:
    p = _cache_path(cfg)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def _save_cache(cfg: Config, data: dict) -> None:
    p = _cache_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def fetch_china_macro(cfg: Config) -> dict:
    """Fetch China macro snapshot. Cached per-day."""
    cached = _load_cache(cfg)
    if cached:
        return cached

    data = {}

    # PMI
    data["pmi"] = _pplx_query(cfg, (
        "中国最新一期官方制造业 PMI 和财新制造业 PMI 各是多少？"
        "各分项（新订单、新出口订单、就业、生产）表现如何？"
        "用中文简洁回复，只列关键数据，3-5 行。"
    ), max_tokens=250)

    # PBOC operations
    data["pboc"] = _pplx_query(cfg, (
        "中国人民银行最近一周的公开市场操作情况：逆回购/MLF 投放量、"
        "净投放还是净回笼？最新 LPR 和存款准备金率是多少？"
        "用中文简洁回复，3-4 行。"
    ), max_tokens=200)

    # Property
    data["property"] = _pplx_query(cfg, (
        "中国最近一周 30 大中城市商品房成交面积情况如何？"
        "同比和环比变化？一二三线城市有什么分化？"
        "用中文 2-3 行简洁回复。"
    ), max_tokens=200)

    _save_cache(cfg, data)
    return data


def format_china_macro_panel(data: dict) -> str:
    lines = ["🇨🇳 <b>中国高频数据</b>"]
    if data.get("pmi"):
        lines.append(f"\n<b>PMI</b>\n{data['pmi']}")
    if data.get("pboc"):
        lines.append(f"\n<b>央行操作</b>\n{data['pboc']}")
    if data.get("property"):
        lines.append(f"\n<b>地产成交</b>\n{data['property']}")
    return "\n".join(lines)


def format_china_macro_for_analyst(data: dict) -> str:
    lines = ["# China High-Frequency Macro Data"]
    if data.get("pmi"):
        lines.append(f"\n## PMI\n{data['pmi']}")
    if data.get("pboc"):
        lines.append(f"\n## PBOC Operations\n{data['pboc']}")
    if data.get("property"):
        lines.append(f"\n## Property Transactions\n{data['property']}")
    return "\n".join(lines)
