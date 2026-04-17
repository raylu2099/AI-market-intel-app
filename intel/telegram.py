"""Telegram bot API sender with auto-splitting for long messages."""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request

from .config import Config


TG_MAX_CHARS = 4096
# Leave headroom; we'll split at paragraph boundaries at this size.
SAFE_CHARS = 3800


def split_message(text: str, limit: int = SAFE_CHARS) -> list[str]:
    """Split text into TG-safe chunks on paragraph (then line) boundaries."""
    if len(text) <= limit:
        return [text]
    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        cut = remaining.rfind("\n\n", 0, limit)
        if cut == -1:
            cut = remaining.rfind("\n", 0, limit)
        if cut == -1:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    return chunks


def _strip_html(text: str) -> str:
    """Fallback: remove all HTML tags for plain-text send when HTML parsing fails."""
    import re
    text = re.sub(r"</?[a-zA-Z][^>]*>", "", text)
    # Replace HTML entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return text


def _post_tg(cfg: Config, text: str, parse_mode: str | None) -> tuple[bool, int]:
    """Single POST attempt. Returns (ok, http_code). http_code 0 on network error."""
    params = {
        "chat_id": cfg.telegram_chat_id,
        "text": text[:TG_MAX_CHARS],
        "disable_web_page_preview": "true",
    }
    if parse_mode:
        params["parse_mode"] = parse_mode
    data = urllib.parse.urlencode(params).encode()
    url = f"https://api.telegram.org/bot{cfg.telegram_bot_token}/sendMessage"
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return bool(json.loads(resp.read().decode()).get("ok")), 200
    except urllib.error.HTTPError as e:
        return False, e.code
    except Exception:
        return False, 0


def send_message(
    cfg: Config, text: str, parse_mode: str = "HTML", retries: int = 3
) -> bool:
    """
    Send with retry on 429. On 400 (bad HTML), auto-fallback to plain text.
    """
    import time

    for attempt in range(retries):
        ok, code = _post_tg(cfg, text, parse_mode)
        if ok:
            return True
        if code == 429 and attempt < retries - 1:
            wait = 2 ** (attempt + 1)
            print(f"[telegram] 429 rate-limited, retry in {wait}s", file=sys.stderr)
            time.sleep(wait)
            continue
        if code == 400 and parse_mode:
            # HTML parse error — strip tags and retry as plain text
            print(
                f"[telegram] HTTP 400 with HTML parse, falling back to plain text",
                file=sys.stderr,
            )
            plain = _strip_html(text)
            ok2, code2 = _post_tg(cfg, plain, None)
            if ok2:
                return True
            print(f"[telegram] plain fallback also failed: HTTP {code2}", file=sys.stderr)
            return False
        if code == 0 and attempt < retries - 1:
            time.sleep(1)
            continue
        print(f"[telegram] send failed: HTTP {code}", file=sys.stderr)
        return False
    return False


def send_long(cfg: Config, text: str, parse_mode: str = "HTML") -> tuple[int, int]:
    """Split and send. Returns (sent_count, total_count)."""
    parts = split_message(text)
    sent = 0
    for p in parts:
        if send_message(cfg, p, parse_mode=parse_mode):
            sent += 1
        else:
            break
    return sent, len(parts)
