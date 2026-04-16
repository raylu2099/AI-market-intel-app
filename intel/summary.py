"""
Lightweight summary helpers for light slots.

Two-step approach for reliability:
  Step 1: search_articles() — gets real, verified URLs (same function as deep
          slots). This populates the archive.
  Step 2: translate_headlines() — cheap Perplexity sonar call that ONLY
          translates the English headlines to Chinese. No search, no synthesis.

This eliminates the risk of Perplexity generating confabulated news when
search_results are empty.
"""
from __future__ import annotations

import json
import sys
import urllib.request

from .config import Config
from .cost_tracker import record_cost
from .search import PPLX_ENDPOINT, SearchQuery, search_articles
from .storage import Article, dedupe_articles


def translate_headlines(
    cfg: Config,
    articles: list[Article],
    context: str = "",
) -> str:
    """
    Translate English article headlines to Chinese via a cheap Perplexity call.
    No search — pure text translation. Returns a numbered Chinese list.
    """
    if not articles:
        return "（无新闻）"

    lines = []
    for i, a in enumerate(articles[:15], 1):
        pub = a.publisher or "unknown"
        lines.append(f"{i}. {a.title} [{pub}]")
    headline_block = "\n".join(lines)

    prompt = (
        f"{context}\n\n"
        f"以下是英文新闻标题列表，请将每条翻译为简体中文。"
        f"保留方括号内的来源标签、公司名、人名、股票代码原样不翻译。"
        f"保持编号格式，每条一行。只输出翻译后的列表，不加前后说明。\n\n"
        f"{headline_block}"
    )

    body = {
        "model": cfg.pplx_model_search,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 800,
        "temperature": 0.1,
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
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        cost = data.get("usage", {}).get("cost", {}).get("total_cost", 0)
        if cost:
            record_cost("perplexity_translate", cost)
            print(f"[cost] translate_headlines: ${cost:.5f}", file=sys.stderr)
        return (
            data.get("choices", [{}])[0]
            .get("message", {}).get("content", "")
        ).strip()
    except Exception as e:
        print(f"[summary] translate failed: {e}", file=sys.stderr)
        return headline_block  # fallback: show English


def search_and_translate(
    cfg: Config,
    queries: list[SearchQuery],
    context: str = "",
) -> tuple[str, list[Article]]:
    """
    Two-step: search for real articles, then translate headlines.
    Returns (chinese_headline_list, articles_for_archive).
    """
    articles = search_articles(cfg, queries)
    articles = dedupe_articles(articles)
    chinese_text = translate_headlines(cfg, articles, context=context)
    return chinese_text, articles
