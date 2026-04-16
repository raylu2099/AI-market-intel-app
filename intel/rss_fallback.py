"""
A5: Google News RSS fallback when Perplexity returns 0 results.
Pure stdlib — no API key needed.
"""
from __future__ import annotations

import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape

from .storage import Article


GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"


def fetch_google_news(query: str, max_results: int = 15) -> list[Article]:
    """Fetch articles from Google News RSS. Free, no API key."""
    url = GOOGLE_NEWS_RSS.format(query=urllib.parse.quote(query))
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; market-intel/1.0)"
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read().decode("utf-8")
    except Exception:
        return []

    articles = []
    try:
        root = ET.fromstring(data)
        for item in root.findall(".//item")[:max_results]:
            title = unescape(item.findtext("title") or "")
            link = item.findtext("link") or ""
            pub_date = item.findtext("pubDate") or ""
            source_el = item.find("source")
            publisher = source_el.text if source_el is not None else ""

            if not link:
                continue
            aid = Article.make_id(link)
            articles.append(
                Article(
                    id=aid,
                    url=link,
                    title=title,
                    publisher=publisher,
                    date=pub_date[:10] if pub_date else "",
                    snippet="",
                    source="google_news_rss",
                )
            )
    except ET.ParseError:
        pass

    return articles
