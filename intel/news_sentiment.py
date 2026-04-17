"""
Alpha Vantage News Sentiment — per-article sentiment scores for watchlist.

Unique value: provides NUMERIC sentiment per news article (Bearish/Neutral/
Bullish with score), something Perplexity and yfinance don't provide.

Free tier: 25 calls/day. We batch all watchlist tickers in one call (supports
comma-separated tickers param), so 1 call per slot = 25 slots/day headroom.

Requires ALPHA_VANTAGE_API_KEY in .env. Gracefully no-ops if missing.
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import requests as _requests

from .config import Config


AV_ENDPOINT = "https://www.alphavantage.co/query"


@dataclass
class TickerSentiment:
    ticker: str
    name: str = ""
    article_count: int = 0
    bullish_pct: float = 0.0
    bearish_pct: float = 0.0
    neutral_pct: float = 0.0
    avg_score: float = 0.0   # -1 to +1
    dominant_label: str = ""  # "Bullish" / "Bearish" / "Neutral" / "Mixed"
    top_positive: str = ""    # top positive headline
    top_negative: str = ""    # top negative headline
    err: str = ""


def _classify(score: float) -> str:
    if score >= 0.35:
        return "Bullish"
    if score >= 0.15:
        return "Somewhat-Bullish"
    if score > -0.15:
        return "Neutral"
    if score > -0.35:
        return "Somewhat-Bearish"
    return "Bearish"


def _cache_path(cfg: Config) -> Path:
    from .timeutil import today_str
    return cfg.data_dir / "cache" / f"av_news_sentiment_{today_str(cfg.market_tz)}.json"


def _fetch_one_ticker(key: str, ticker: str, limit: int = 50) -> list:
    """Fetch news feed for a single ticker."""
    try:
        resp = _requests.get(
            AV_ENDPOINT,
            params={
                "function": "NEWS_SENTIMENT",
                "tickers": ticker,
                "limit": limit,
                "apikey": key,
            },
            timeout=20,
        )
        data = resp.json()
        if "Note" in data or "Information" in data:
            return []
        return data.get("feed", [])
    except Exception as e:
        print(f"[news_sentiment] {ticker} error: {e}", file=sys.stderr)
        return []


def fetch_news_sentiment(
    cfg: Config, tickers: list[tuple[str, str]], use_cache: bool = True
) -> list[TickerSentiment]:
    """
    Fetch per-ticker news sentiment. Iterates one call per ticker (free tier
    is 25/day, so 5 watchlist tickers = 5 calls fits easily if called once/day).

    Caches result for the day to avoid re-fetching on multi-slot runs.
    """
    key = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
    results = [TickerSentiment(ticker=t, name=n) for t, n in tickers]
    if not key:
        for r in results:
            r.err = "no API key"
        return results

    # Try cache
    cache = _cache_path(cfg)
    if use_cache and cache.exists():
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
            cached_by_ticker = {c["ticker"]: c for c in cached}
            for r in results:
                if r.ticker in cached_by_ticker:
                    for k, v in cached_by_ticker[r.ticker].items():
                        setattr(r, k, v)
            return results
        except Exception:
            pass

    # Fetch per-ticker
    by_ticker = {r.ticker: r for r in results}
    for ticker, _name in tickers:
        feed = _fetch_one_ticker(key, ticker)
        time.sleep(0.8)  # politeness for free tier
        if not feed:
            by_ticker[ticker].err = "no news or rate limited"
            continue

        scores = []
        for item in feed:
            title = item.get("title", "")
            for ts in item.get("ticker_sentiment", []):
                if ts.get("ticker") != ticker:
                    continue
                try:
                    score = float(ts.get("ticker_sentiment_score", 0))
                    scores.append((score, title))
                except (ValueError, TypeError):
                    continue

        r = by_ticker[ticker]
        if not scores:
            r.err = "no ticker-tagged scores"
            continue
        r.article_count = len(scores)
        bullish = sum(1 for s, _ in scores if s >= 0.15)
        bearish = sum(1 for s, _ in scores if s <= -0.15)
        neutral = len(scores) - bullish - bearish
        r.bullish_pct = bullish / len(scores) * 100
        r.bearish_pct = bearish / len(scores) * 100
        r.neutral_pct = neutral / len(scores) * 100
        r.avg_score = sum(s for s, _ in scores) / len(scores)
        r.dominant_label = _classify(r.avg_score)
        sorted_scores = sorted(scores, key=lambda x: x[0], reverse=True)
        if sorted_scores:
            r.top_positive = sorted_scores[0][1][:100]
            r.top_negative = sorted_scores[-1][1][:100]

    # Save cache
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(
            json.dumps([asdict(r) for r in results], ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"[news_sentiment] cache write failed: {e}", file=sys.stderr)

    return results


def format_sentiment_panel(snaps: list[TickerSentiment]) -> str:
    lines = ["🎭 <b>新闻情绪 (Alpha Vantage)</b>"]
    for s in snaps:
        if s.err:
            continue
        emoji = "🟢" if s.avg_score >= 0.15 else ("🔴" if s.avg_score <= -0.15 else "⚪")
        lines.append(
            f"  {emoji} <b>{s.name}</b> ({s.ticker}): {s.dominant_label} "
            f"({s.avg_score:+.2f}) | {s.article_count} 篇"
        )
        lines.append(
            f"    多 {s.bullish_pct:.0f}% / 空 {s.bearish_pct:.0f}% / 中 {s.neutral_pct:.0f}%"
        )
    return "\n".join(lines)


def format_sentiment_for_analyst(snaps: list[TickerSentiment]) -> str:
    lines = ["# News Sentiment (Alpha Vantage, per-ticker aggregate)"]
    for s in snaps:
        if s.err:
            lines.append(f"- {s.ticker}: {s.err}")
            continue
        lines.append(
            f"\n## {s.name} ({s.ticker})"
        )
        lines.append(
            f"- Articles analyzed: {s.article_count}"
        )
        lines.append(
            f"- Avg sentiment score: {s.avg_score:+.3f} → {s.dominant_label}"
        )
        lines.append(
            f"- Distribution: {s.bullish_pct:.0f}% bullish, "
            f"{s.bearish_pct:.0f}% bearish, {s.neutral_pct:.0f}% neutral"
        )
        if s.top_positive:
            lines.append(f"- Most bullish headline: {s.top_positive}")
        if s.top_negative:
            lines.append(f"- Most bearish headline: {s.top_negative}")
    lines.append(
        "\n- Interpretation: score > +0.35 = strongly bullish; < -0.35 = strongly bearish. "
        "Extreme readings (80%+ one-sided) may be contrarian signals."
    )
    return "\n".join(lines)
