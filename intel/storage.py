"""
Storage layer. Articles are stored as JSONL so they're easy to grep, diff,
and back up. Analyses are Markdown. No database.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from .config import Config
from .timeutil import now_utc


@dataclass
class Article:
    id: str                 # sha1 of URL
    url: str
    title: str
    publisher: str
    date: str               # publish date (YYYY-MM-DD) as reported by source
    snippet: str
    body: str | None = None
    fetched: bool = False
    paywalled: bool = False
    fetched_at: str = ""    # ISO UTC timestamp
    source: str = "perplexity"
    extra: dict = field(default_factory=dict)

    @classmethod
    def make_id(cls, url: str) -> str:
        return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, line: str) -> "Article":
        d = json.loads(line)
        d.setdefault("extra", {})
        return cls(**d)


def save_articles(path: Path, articles: Iterable[Article], mode: str = "w") -> int:
    """Persist articles to JSONL. mode='w' (default) replaces the file;
    mode='a' appends. Replace is correct for slot runs that treat each day's
    archive as a snapshot — re-running a slot should not create duplicates."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open(mode, encoding="utf-8") as f:
        for a in articles:
            if not a.fetched_at:
                a.fetched_at = now_utc().isoformat(timespec="seconds")
            f.write(a.to_json() + "\n")
            count += 1
    return count


def load_articles(path: Path) -> list[Article]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(Article.from_json(line))
            except Exception:
                continue
    return out


def load_articles_glob(root: Path, pattern: str = "*/articles.jsonl") -> list[Article]:
    """Load every articles.jsonl matching a glob under root."""
    if not root.exists():
        return []
    out = []
    for p in sorted(root.glob(pattern)):
        out.extend(load_articles(p))
    return out


def save_analysis(cfg: Config, category: str, date_str: str, content: str) -> Path:
    path = cfg.analyses_dir(category) / f"{date_str}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def load_recent_analyses(cfg: Config, category: str, days: int) -> list[tuple[str, str]]:
    """Return list of (date_str, content) for the last `days` daily analyses."""
    root = cfg.analyses_dir(category)
    if not root.exists():
        return []
    files = sorted(root.glob("*.md"))
    files = files[-days:]
    return [(p.stem, p.read_text(encoding="utf-8")) for p in files]


def save_push(cfg: Config, date_str: str, slot: str, messages: list[str]) -> Path:
    path = cfg.pushes_dir(date_str) / f"{slot}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    sep = "\n\n---[SPLIT]---\n\n"
    path.write_text(sep.join(messages), encoding="utf-8")
    return path


def dedupe_articles(articles: list[Article]) -> list[Article]:
    """Keep first occurrence of each article by id."""
    seen = set()
    out = []
    for a in articles:
        if a.id in seen:
            continue
        seen.add(a.id)
        out.append(a)
    return out
