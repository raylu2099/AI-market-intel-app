"""
market_close slot: deep Claude analysis of the US market close with watchlist
focus. Same pipeline shape as china_open but different search queries and
prompt.
"""
from __future__ import annotations

from ..claude_analyst import analyze, load_prompt
from ..config import Config
from ..cftc import fetch_cot_data, format_cot_for_analyst
from ..earnings import fetch_all_earnings, format_earnings_for_analyst
from ..fred import fetch_fred_indicators, format_fred_for_analyst
from ..news_sentiment import fetch_news_sentiment as fetch_av_sentiment
from ..news_sentiment import format_sentiment_for_analyst as format_av_for_analyst
from ..sector_rotation import compute_sector_rotation, format_sector_for_analyst
from ..sentiment import fetch_sentiment, format_sentiment_for_analyst
from ..events import upcoming_earnings
from ..fetch import enrich_with_bodies
from ..macro_regime import compute_regime, format_regime_for_analyst
from ..prices import MACRO_TICKERS, RADAR_TICKERS, fetch_quotes
from ..search import SearchQuery, search_articles
from ..storage import dedupe_articles, load_recent_analyses, save_analysis
from ..technicals import compute_technicals, format_technicals_for_analyst
from ..telegram import split_message
from ..timeutil import now_pt, today_str
from ..valuations import fetch_valuations, format_valuations_for_analyst
from .base import (
    SlotResult,
    archive_articles,
    format_article_block,
    format_history_index,
    load_recent_articles,
)


CATEGORY = "market_close"
SLOT_NAME = "close"
CORE_DOMAINS = [
    "reuters.com", "bloomberg.com", "wsj.com", "ft.com",
    "cnbc.com", "barrons.com", "marketwatch.com", "seekingalpha.com",
    "apnews.com",
]


def _queries(cfg: Config) -> list[SearchQuery]:
    watchlist_names = ", ".join(name for _, name in cfg.watchlist)
    watchlist_tickers = ", ".join(t for t, _ in cfg.watchlist)
    return [
        SearchQuery(
            prompt=(
                "Find the most important news about the US stock market close "
                "today: S&P 500, Nasdaq, Dow Jones performance, sector rotation, "
                "and major market-moving events from the last 24 hours."
            ),
            domain_filter=CORE_DOMAINS,
            recency="day",
            max_tokens=100,
            search_context="high",
        ),
        SearchQuery(
            prompt=(
                f"Find news from the last 24 hours about these specific stocks: "
                f"{watchlist_names} ({watchlist_tickers}). Focus on earnings, "
                f"analyst rating changes, product events, and regulatory news."
            ),
            domain_filter=CORE_DOMAINS,
            recency="day",
            max_tokens=100,
            search_context="high",
        ),
        SearchQuery(
            prompt=(
                "Find news about US macro conditions from the last 24 hours: "
                "Federal Reserve speeches, CPI/PCE/NFP data, Treasury yields, "
                "dollar, oil, and gold."
            ),
            domain_filter=CORE_DOMAINS,
            recency="day",
            max_tokens=100,
            search_context="high",
        ),
    ]


def _build_user_prompt(
    cfg: Config,
    today_articles: list,
    history_articles: list,
    past_analyses: list[tuple[str, str]],
    tech_snaps=None,
    val_snaps=None,
    macro_quotes=None,
    regime=None,
    earnings_profiles=None,
    sentiment=None,
    cot_data=None,
    sector_perfs=None,
    fred_data=None,
    av_sentiment=None,
) -> str:
    watchlist_str = ", ".join(f"{t} ({n})" for t, n in cfg.watchlist)
    parts = [
        f"# Today's date (US Pacific): {now_pt().strftime('%Y-%m-%d %A')}",
        f"# Watchlist: {watchlist_str}",
        "",
    ]

    # Quantitative data sections
    if regime:
        parts.append(format_regime_for_analyst(regime))
        parts.append("")

    if tech_snaps:
        parts.append(format_technicals_for_analyst(tech_snaps))
        parts.append("")

    if val_snaps:
        parts.append(format_valuations_for_analyst(val_snaps))
        parts.append("")

    if earnings_profiles:
        parts.append(format_earnings_for_analyst(earnings_profiles))
        parts.append("")

    if sentiment:
        parts.append(format_sentiment_for_analyst(sentiment))
        parts.append("")

    if cot_data:
        parts.append(format_cot_for_analyst(cot_data))
        parts.append("")

    if sector_perfs:
        parts.append(format_sector_for_analyst(sector_perfs))
        parts.append("")

    if fred_data:
        parts.append(format_fred_for_analyst(fred_data))
        parts.append("")

    if av_sentiment:
        parts.append(format_av_for_analyst(av_sentiment))
        parts.append("")

    if macro_quotes:
        parts.append("# Current Macro Prices")
        for q in macro_quotes:
            if q.ok:
                parts.append(f"- {q.name} ({q.ticker}): {q.last:.2f} ({q.pct:+.2f}%)")
        parts.append("")

    parts.extend([
        f"# Today's articles ({len(today_articles)} items)",
        "",
        format_article_block(today_articles, include_body=True),
        "",
        f"# Historical article index (last {cfg.history_window_days} days)",
        "",
        format_history_index(history_articles),
        "",
        f"# Your past analyses (last {cfg.history_window_days} days)",
        "",
    ])
    if past_analyses:
        for date_str, content in past_analyses[-15:]:
            parts.append(f"## Analysis from {date_str}")
            parts.append("")
            parts.append(content)
            parts.append("")
    else:
        parts.append("(no past analyses — day 1 of operation, continuity "
                     "section should note 'data accumulating')")
        parts.append("")
    parts.append("---")
    parts.append("")
    parts.append(
        "Produce the close briefing now, following the system prompt format. "
        "Cite with [A1]..[A{}]. CRITICAL: anchor your position theses to the "
        "quantitative data provided (technicals, valuations, regime). Do NOT "
        "recommend a long on a stock with RSI > 75 without flagging overbought "
        "risk. Validate positions against the current macro regime.".format(
            len(today_articles)
        )
    )
    return "\n".join(parts)


def run(cfg: Config) -> SlotResult:
    date_str = today_str(cfg.market_tz)

    articles = search_articles(cfg, _queries(cfg))
    articles = dedupe_articles(articles)
    enrich_with_bodies(articles)
    archive_articles(cfg, CATEGORY, date_str, articles)

    history = load_recent_articles(cfg, CATEGORY, cfg.history_window_days)
    past_analyses = load_recent_analyses(cfg, CATEGORY, cfg.history_window_days)

    # Quantitative data
    tech_snaps = compute_technicals(list(cfg.watchlist))
    val_snaps = fetch_valuations(list(cfg.watchlist))
    earnings_profiles = fetch_all_earnings(cfg)
    macro_quotes = fetch_quotes(MACRO_TICKERS + RADAR_TICKERS)
    regime = compute_regime()
    sentiment = fetch_sentiment(list(cfg.watchlist))
    cot_data = fetch_cot_data()
    sector_perfs = compute_sector_rotation()
    fred_data = fetch_fred_indicators()
    av_sentiment = fetch_av_sentiment(cfg, list(cfg.watchlist))

    system_prompt = load_prompt(cfg, "market_close_analyst")
    user_prompt = _build_user_prompt(
        cfg, articles, history, past_analyses,
        tech_snaps, val_snaps, macro_quotes, regime, earnings_profiles,
        sentiment, cot_data, sector_perfs, fred_data, av_sentiment,
    )
    analysis_md = analyze(cfg, system_prompt, user_prompt)
    save_analysis(cfg, CATEGORY, date_str, analysis_md)

    # P9: Tomorrow's earnings alert for watchlist
    earnings_alert = upcoming_earnings(cfg, horizon_days=2)
    earnings_section = ""
    if earnings_alert and "无" not in earnings_alert:
        earnings_section = f"\n\n⚠️ <b>明日财报预警</b>\n{earnings_alert}"

    header = f"🏁 <b>US Close</b> — {now_pt():%a %m/%d} 16:00 ET"
    full = f"{header}\n\n{analysis_md}{earnings_section}"
    messages = split_message(full)

    return SlotResult(
        slot=SLOT_NAME,
        category=CATEGORY,
        date_str=date_str,
        articles=articles,
        messages=messages,
        analysis_md=analysis_md,
    )
