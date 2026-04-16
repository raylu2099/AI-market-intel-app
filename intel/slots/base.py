"""Common building blocks for slot pipelines."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..config import Config
from ..storage import Article, load_articles, save_articles
from ..timeutil import now_utc


@dataclass
class SlotResult:
    slot: str
    category: str
    date_str: str
    articles: list[Article]
    messages: list[str]
    analysis_md: str | None = None


def format_article_block(articles: list[Article], include_body: bool = True) -> str:
    """Format articles as a numbered list suitable for feeding to the analyst."""
    lines = []
    for i, a in enumerate(articles, 1):
        aid = f"A{i}"
        header = (
            f"[{aid}] {a.title}\n"
            f"    publisher: {a.publisher}\n"
            f"    url: {a.url}\n"
            f"    date: {a.date or 'unknown'}\n"
            f"    source_type: {'full_text' if a.fetched else ('paywalled_snippet' if a.paywalled else 'snippet')}"
        )
        lines.append(header)
        if include_body:
            if a.fetched and a.body:
                body = a.body.strip()
                if len(body) > 1800:
                    body = body[:1800] + "…"
                lines.append(f"    body:\n        {body.replace(chr(10), chr(10)+'        ')}")
            elif a.snippet:
                lines.append(f"    snippet: {a.snippet}")
        lines.append("")
    return "\n".join(lines)


def format_history_index(articles: list[Article]) -> str:
    """
    Compact title/date index of historical articles — used as cheap context
    for cross-day pattern matching without burning tokens on full bodies.
    """
    if not articles:
        return "(no historical articles in window)"
    lines = []
    for a in articles:
        date = a.date or a.fetched_at[:10]
        lines.append(f"- [{date}] [{a.publisher}] {a.title}")
    return "\n".join(lines)


def archive_path(cfg: Config, category: str, date_str: str, slot_sub: str = "") -> Path:
    """Return the JSONL path for a slot's archived sources."""
    if slot_sub:
        return cfg.sources_dir(category, f"{date_str}_{slot_sub}") / "articles.jsonl"
    return cfg.sources_dir(category, date_str) / "articles.jsonl"


def archive_articles(
    cfg: Config, category: str, date_str: str, articles: list[Article], slot_sub: str = ""
) -> Path:
    path = archive_path(cfg, category, date_str, slot_sub)
    save_articles(path, articles)
    return path


def load_recent_articles(
    cfg: Config, category: str, days: int
) -> list[Article]:
    """Load all articles from the last `days` days under a category."""
    from ..timeutil import days_back, now_in
    import zoneinfo
    tz = cfg.market_tz
    wanted = set(days_back(tz, days))
    root = cfg.sources_dir(category)
    if not root.exists():
        return []
    out = []
    for subdir in sorted(root.iterdir()):
        if not subdir.is_dir():
            continue
        # subdir name is YYYY-MM-DD or YYYY-MM-DD_<sub>
        date_part = subdir.name.split("_")[0]
        if date_part in wanted:
            jsonl = subdir / "articles.jsonl"
            if jsonl.exists():
                out.extend(load_articles(jsonl))
    return out
