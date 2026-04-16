"""
Smoke test for Phase 1 modules. Runs a single real query against Perplexity,
fetches a handful of articles, persists them to data/, and does a round-trip.

Usage: python -m tests.smoke
"""
from __future__ import annotations

import sys

from intel.config import load_config
from intel.fetch import enrich_with_bodies
from intel.search import SearchQuery, search_articles
from intel.storage import (
    Article,
    dedupe_articles,
    load_articles,
    save_articles,
)
from intel.telegram import split_message


def main() -> int:
    print("--- loading config ---")
    cfg = load_config()
    print(f"data_dir   = {cfg.data_dir}")
    print(f"watchlist  = {[t for t, _ in cfg.watchlist]}")
    print(f"history    = {cfg.history_window_days} days")

    print("\n--- split_message test ---")
    fake = "para1\n\n" + ("x" * 3000) + "\n\n" + ("y" * 3000) + "\n\ntail"
    parts = split_message(fake)
    print(f"input {len(fake)} chars -> {len(parts)} parts "
          f"(sizes: {[len(p) for p in parts]})")

    print("\n--- search test (Perplexity, 1 query) ---")
    queries = [
        SearchQuery(
            prompt=(
                "Find the most important news articles about China politics, "
                "economy, and military from the last 24 hours."
            ),
            domain_filter=[
                "reuters.com", "bloomberg.com", "ft.com", "wsj.com",
                "scmp.com", "nikkei.com", "apnews.com",
            ],
            recency="day",
            max_tokens=120,
            search_context=cfg.pplx_search_context,
        ),
    ]
    articles = search_articles(cfg, queries)
    articles = dedupe_articles(articles)
    print(f"got {len(articles)} unique articles")
    for i, a in enumerate(articles[:5], 1):
        print(f"  {i}. [{a.publisher:20s}] {a.title[:60]}")
        print(f"     {a.url[:90]}")

    if not articles:
        print("NO articles returned. Aborting fetch/storage test.")
        return 1

    print("\n--- fetch test (first 3 articles) ---")
    sample = articles[:3]
    enrich_with_bodies(sample)
    for a in sample:
        status = (
            f"fetched={a.fetched} paywalled={a.paywalled} "
            f"body_chars={len(a.body) if a.body else 0}"
        )
        print(f"  [{a.publisher[:20]:20s}] {status}")

    print("\n--- storage round-trip ---")
    out_path = cfg.data_dir / "_smoke" / "articles.jsonl"
    # Clear any prior run
    if out_path.exists():
        out_path.unlink()
    n = save_articles(out_path, sample)
    reloaded = load_articles(out_path)
    assert len(reloaded) == n, "round-trip count mismatch"
    assert all(isinstance(a, Article) for a in reloaded)
    print(f"  wrote + reloaded {n} articles at {out_path}")

    print("\nOK — Phase 1 smoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
