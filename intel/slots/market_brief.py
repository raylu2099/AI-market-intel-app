"""
Light market briefing slots: premarket / open / midday.

Two-step search+translate: first gets real URLs via search_articles(),
then translates English headlines to Chinese. No confabulation risk.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import Config
from ..events import format_event_calendar
from ..prices import (
    MACRO_TICKERS,
    RADAR_TICKERS,
    fetch_quotes,
    format_macro,
    format_watchlist,
)
from ..search import SearchQuery
from ..summary import search_and_translate
from ..macro_regime import compute_regime, format_regime_panel
from ..sentiment import fetch_sentiment, format_sentiment_panel
from ..technicals import compute_technicals, format_technicals_panel
from ..telegram import split_message
from ..timeutil import now_pt, today_str
from .base import SlotResult, archive_articles


CATEGORY = "market"
# Broad but curated: includes open-access + partially-open financial news.
# Avoids YouTube, social media, government sites that add noise.
MARKET_DOMAINS = [
    "cnbc.com", "investing.com", "marketwatch.com", "finance.yahoo.com",
    "barrons.com", "seekingalpha.com", "thestreet.com",
    "businessinsider.com", "morningstar.com", "benzinga.com",
    "reuters.com", "bloomberg.com", "wsj.com", "ft.com", "apnews.com",
]


@dataclass
class MarketBriefSpec:
    slot_name: str
    header_emoji: str
    header_label: str
    header_time_label: str
    search_prompts: list[str]
    include_watchlist: bool = True
    include_macro: bool = True
    include_radar: bool = False
    include_events: bool = False
    include_technicals: bool = False


def _queries(spec: MarketBriefSpec) -> list[SearchQuery]:
    return [
        SearchQuery(
            prompt=p,
            domain_filter=MARKET_DOMAINS,
            recency="day",
            max_tokens=80,
            search_context="high",
        )
        for p in spec.search_prompts
    ]


def run_market_brief(cfg: Config, spec: MarketBriefSpec) -> SlotResult:
    date_str = today_str(cfg.market_tz)

    chinese_headlines, articles = search_and_translate(
        cfg, _queries(spec), context=spec.header_label
    )

    archive_articles(cfg, CATEGORY, date_str, articles, slot_sub=spec.slot_name)

    pt = now_pt()
    header = (
        f"{spec.header_emoji} <b>{spec.header_label}</b> — "
        f"{pt:%a %m/%d} {spec.header_time_label}"
    )
    parts = [header]

    if spec.include_watchlist:
        wl_quotes = fetch_quotes(cfg.watchlist)
        parts.append("📊 <b>美股关注</b>\n" + format_watchlist(wl_quotes))

    if spec.include_macro:
        macro_quotes = fetch_quotes(MACRO_TICKERS)
        parts.append("💰 <b>宏观</b>\n" + format_macro(macro_quotes))

    if spec.include_radar:
        radar_quotes = fetch_quotes(RADAR_TICKERS)
        parts.append("🔭 <b>市场雷达</b>\n" + format_watchlist(radar_quotes))

    if spec.include_technicals:
        tech_snaps = compute_technicals(cfg.watchlist)
        parts.append(format_technicals_panel(tech_snaps))
        regime = compute_regime()
        parts.append(format_regime_panel(regime))
        sentiment = fetch_sentiment(cfg.watchlist)
        parts.append(format_sentiment_panel(sentiment))

    if spec.include_events:
        parts.append(format_event_calendar(cfg))

    parts.append(f"📰 <b>要闻 ({len(articles)} 篇真实来源)</b>\n{chinese_headlines}")

    # P4: Split into core (first screen) + detail (scrollable)
    # Core = header + watchlist + macro; Detail = radar + technicals + events + news
    core_parts = [p for p in parts[:4]]  # header, watchlist, macro at most
    detail_parts = [p for p in parts[4:]]  # radar, technicals, regime, events, news

    messages = []
    if core_parts:
        messages.extend(split_message("\n\n".join(core_parts)))
    if detail_parts:
        messages.extend(split_message("\n\n".join(detail_parts)))

    return SlotResult(
        slot=spec.slot_name,
        category=CATEGORY,
        date_str=date_str,
        articles=articles,
        messages=messages,
    )


PREMARKET_SPEC = MarketBriefSpec(
    slot_name="premarket",
    header_emoji="📰",
    header_label="盘前简报",
    header_time_label="06:00 PT",
    search_prompts=[
        "Find the most important overnight market developments affecting US stocks: Asia and Europe index moves, US equity futures, and major pre-market stock movers.",
        "Find the most important macro releases, Federal Reserve speeches, commodity moves (oil, gold, copper), and dollar index changes in the last 16 hours.",
    ],
    include_radar=True,
    include_events=True,
    include_technicals=True,
)

OPEN_SPEC = MarketBriefSpec(
    slot_name="open",
    header_emoji="🔔",
    header_label="开盘快报",
    header_time_label="09:30 ET",
    search_prompts=[
        "Find the most important headlines for the US stock market opening today: pre-market movers, analyst actions, earnings reactions, and breaking news.",
    ],
    include_macro=False,
)

MIDDAY_SPEC = MarketBriefSpec(
    slot_name="midday",
    header_emoji="📊",
    header_label="午盘简报",
    header_time_label="12:30 ET",
    search_prompts=[
        "Find the most important US stock market developments from the morning session today: sector rotation, notable stock moves, macro data releases, and analyst actions.",
    ],
)
