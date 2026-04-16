#!/usr/bin/env python3
"""
Data sanitization (#15). Strips article bodies and snippets from archived
JSONL, keeping only metadata (id, url, title, publisher, date, paywalled).

Useful for:
- Sharing archive structure without copyrighted article text
- Reducing disk usage
- Public GitHub samples

Usage:
    python bin/sanitize.py data/sources/china/2026-04-15/articles.jsonl > sanitized.jsonl
    python bin/sanitize.py --all-under data/sources/           # in-place strip
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def sanitize_line(line: str) -> str:
    d = json.loads(line)
    d.pop("body", None)
    d.pop("snippet", None)
    d.pop("extra", None)
    return json.dumps(d, ensure_ascii=False)


def sanitize_file(path: Path, in_place: bool = False) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    sanitized = [sanitize_line(l) for l in lines if l.strip()]
    if in_place:
        path.write_text("\n".join(sanitized) + "\n", encoding="utf-8")
        print(f"  sanitized {path} ({len(sanitized)} records)", file=sys.stderr)
    else:
        for s in sanitized:
            print(s)


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(f"Usage: {sys.argv[0]} [--all-under <dir>] <file.jsonl>", file=sys.stderr)
        return 1

    if args[0] == "--all-under" and len(args) >= 2:
        root = Path(args[1])
        for p in sorted(root.rglob("*.jsonl")):
            sanitize_file(p, in_place=True)
        return 0

    sanitize_file(Path(args[0]), in_place=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
