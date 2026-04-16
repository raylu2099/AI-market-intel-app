"""
Article fetcher. Tries to download the full HTML and extract clean text via
trafilatura. Bot-blocked or paywalled URLs get `fetched=False, paywalled=True`
and keep the Perplexity snippet as fallback content.
"""
from __future__ import annotations

import time

import requests
import trafilatura

from .storage import Article
from .timeutil import now_utc


UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 15
POLITENESS_DELAY_SEC = 1.5
MIN_BODY_CHARS = 200  # below this we consider extraction a failure


def _fetch_one(url: str) -> tuple[str | None, bool]:
    """
    Return (body_text, paywalled). body_text is None on failure.
    paywalled is True for 401/403 specifically (bot blocking / paywall).
    """
    try:
        r = requests.get(
            url,
            headers={"User-Agent": UA, "Accept-Language": "en,zh;q=0.8"},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
    except Exception:
        return None, False

    if r.status_code in (401, 403):
        return None, True
    if r.status_code >= 400:
        return None, False

    try:
        extracted = trafilatura.extract(
            r.text,
            include_comments=False,
            include_tables=False,
            favor_recall=True,
        )
    except Exception:
        extracted = None

    if extracted and len(extracted) >= MIN_BODY_CHARS:
        return extracted, False
    return None, False


def enrich_with_bodies(articles: list[Article]) -> list[Article]:
    """Mutate articles in place to add fetched bodies. Returns the same list."""
    for i, art in enumerate(articles):
        body, paywalled = _fetch_one(art.url)
        art.fetched_at = now_utc().isoformat(timespec="seconds")
        if body:
            art.body = body
            art.fetched = True
            art.paywalled = False
        else:
            art.body = None
            art.fetched = False
            art.paywalled = paywalled
        if i < len(articles) - 1:
            time.sleep(POLITENESS_DELAY_SEC)
    return articles
