"""
Perplexity as a search probe. We extract the real URL list from
`search_results`, not the synthesized answer, and return Article records.

Running multiple queries against different angles is what gives us source
diversity — a single query tends to cluster on one domain.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from dataclasses import dataclass

from .config import Config
from .cost_tracker import record_cost
from .storage import Article


PPLX_ENDPOINT = "https://api.perplexity.ai/chat/completions"


@dataclass
class SearchQuery:
    prompt: str
    domain_filter: list[str] | None = None
    recency: str = "day"
    max_tokens: int = 100
    search_context: str = "high"


def _call(cfg: Config, query: SearchQuery) -> dict:
    body: dict = {
        "model": cfg.pplx_model_search,
        "messages": [{"role": "user", "content": query.prompt}],
        "max_tokens": query.max_tokens,
        "temperature": 0.1,
        "web_search_options": {"search_context_size": query.search_context},
    }
    if query.recency:
        body["search_recency_filter"] = query.recency
    if query.domain_filter:
        body["search_domain_filter"] = query.domain_filter

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
            record_cost("perplexity_search", cost)
            print(f"[cost] search: ${cost:.5f}", file=sys.stderr)
        return data
    except Exception as e:
        print(f"[search] perplexity call failed: {e}", file=sys.stderr)
        return {}


def _publisher_from_url(url: str) -> str:
    try:
        host = url.split("/")[2]
        if host.startswith("www."):
            host = host[4:]
        if host.startswith("amp."):
            host = host[4:]
        return host
    except Exception:
        return ""


def search_articles(
    cfg: Config,
    queries: list[SearchQuery],
    min_results: int = 3,
) -> list[Article]:
    """
    Run multiple queries, dedupe by URL, return Article records.
    A3: If domain_filter yields < min_results, auto-retry without filter.
    """
    by_id: dict[str, Article] = {}

    def _collect(q: SearchQuery) -> None:
        resp = _call(cfg, q)
        if not resp:
            return
        for r in resp.get("search_results") or []:
            url = (r.get("url") or "").strip()
            if not url:
                continue
            aid = Article.make_id(url)
            if aid in by_id:
                continue
            by_id[aid] = Article(
                id=aid,
                url=url,
                title=(r.get("title") or "").strip(),
                publisher=_publisher_from_url(url),
                date=(r.get("date") or "").strip(),
                snippet=(r.get("snippet") or "").strip(),
                source="perplexity",
            )

    for q in queries:
        _collect(q)

    # A3: Auto-degrade if domain_filter produced too few results
    if len(by_id) < min_results:
        had_filters = any(q.domain_filter for q in queries)
        if had_filters:
            print(
                f"[search] only {len(by_id)} results with domain_filter, "
                f"retrying without filter",
                file=sys.stderr,
            )
            for q in queries:
                if q.domain_filter:
                    fallback = SearchQuery(
                        prompt=q.prompt,
                        domain_filter=None,
                        recency=q.recency,
                        max_tokens=q.max_tokens,
                        search_context=q.search_context,
                    )
                    _collect(fallback)

    # A5: If still < min_results after domain fallback, try Google News RSS
    if len(by_id) < min_results:
        try:
            from .rss_fallback import fetch_google_news
            # Use first query's prompt as search term
            search_term = queries[0].prompt[:80] if queries else "market news"
            rss_articles = fetch_google_news(search_term, max_results=10)
            for a in rss_articles:
                if a.id not in by_id:
                    by_id[a.id] = a
            if rss_articles:
                print(
                    f"[search] RSS fallback added {len(rss_articles)} articles",
                    file=sys.stderr,
                )
        except Exception as e:
            print(f"[search] RSS fallback failed: {e}", file=sys.stderr)

    return list(by_id.values())
