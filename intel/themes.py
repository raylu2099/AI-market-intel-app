"""
Theme tracking (#13). After each deep analysis, extract key themes
and append to rolling theme files under data/themes/<theme_slug>.md.

Each theme file is a chronological log:
---
# Theme: <name>
## 2026-04-15
- <observation from today's analysis>
## 2026-04-14
- ...
---

This gives Claude long-term context per-theme without loading all analyses.
"""
from __future__ import annotations

import re
from pathlib import Path

from .config import Config


THEMES_DIR_NAME = "themes"


def themes_dir(cfg: Config) -> Path:
    d = cfg.data_dir / THEMES_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def slugify(name: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", name.lower().strip())
    return re.sub(r"[\s-]+", "_", slug)[:60]


def append_theme(cfg: Config, theme_name: str, date_str: str, note: str) -> Path:
    slug = slugify(theme_name)
    path = themes_dir(cfg) / f"{slug}.md"
    if not path.exists():
        path.write_text(f"# Theme: {theme_name}\n\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as f:
        f.write(f"## {date_str}\n- {note}\n\n")
    return path


def load_theme(cfg: Config, theme_name: str) -> str:
    slug = slugify(theme_name)
    path = themes_dir(cfg) / f"{slug}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def list_themes(cfg: Config) -> list[str]:
    d = themes_dir(cfg)
    return sorted(p.stem for p in d.glob("*.md"))
