"""Quote helpers backed by yfinance. Intentionally thin — no caching."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Quote:
    ticker: str
    name: str
    last: float | None = None
    prev: float | None = None
    pct: float | None = None
    err: str = ""

    @property
    def ok(self) -> bool:
        return self.err == "" and self.last is not None and self.prev is not None


def fetch_quotes(tickers: list[tuple[str, str]]) -> list[Quote]:
    """Fetch quotes for a list of (ticker, name) pairs. Never raises."""
    try:
        import yfinance as yf
    except ImportError:
        return [Quote(t, n, err="yfinance not installed") for t, n in tickers]

    out = []
    for ticker, name in tickers:
        try:
            fi = yf.Ticker(ticker).fast_info
            last = getattr(fi, "last_price", None) or fi.get("lastPrice")  # type: ignore
            prev = getattr(fi, "previous_close", None) or fi.get("previousClose")  # type: ignore
            if last is not None and prev:
                last_f = float(last)
                prev_f = float(prev)
                out.append(
                    Quote(
                        ticker=ticker,
                        name=name,
                        last=last_f,
                        prev=prev_f,
                        pct=(last_f - prev_f) / prev_f * 100,
                    )
                )
            else:
                out.append(Quote(ticker, name, err="no data"))
        except Exception as e:
            out.append(Quote(ticker, name, err=str(e)[:80]))
    return out


def format_watchlist(quotes: list[Quote]) -> str:
    lines = []
    for q in quotes:
        if not q.ok:
            lines.append(f"• {q.name} ({q.ticker}): —")
            continue
        arrow = "🟢" if (q.pct or 0) >= 0 else "🔴"
        lines.append(
            f"{arrow} <b>{q.name}</b> {q.ticker}: "
            f"${q.last:.2f} ({q.pct:+.2f}%)"
        )
    return "\n".join(lines)


MACRO_TICKERS: list[tuple[str, str]] = [
    ("GC=F", "黄金 XAU"),
    ("USDCNY=X", "USD/CNY"),
    ("^TNX", "10Y 美债"),
    ("^VIX", "VIX"),
    ("DX-Y.NYB", "DXY 美元"),
    ("HG=F", "铜"),
    ("BTC-USD", "Bitcoin"),
]

RADAR_TICKERS: list[tuple[str, str]] = [
    ("SPY", "S&P 500"),
    ("QQQ", "Nasdaq 100"),
    ("IWM", "Russell 2000"),
    ("KWEB", "中概互联"),
    ("XLF", "金融"),
    ("XLE", "能源"),
    ("XLK", "科技"),
]


def format_macro(quotes: list[Quote]) -> str:
    lines = []
    for q in quotes:
        if not q.ok:
            lines.append(f"• {q.name}: —")
            continue
        assert q.last is not None and q.pct is not None
        if q.ticker == "GC=F":
            v = f"${q.last:.1f}"
        elif q.ticker == "USDCNY=X":
            v = f"{q.last:.3f}"
        elif q.ticker == "^TNX":
            v = f"{q.last:.2f}%"
        else:
            v = f"{q.last:.2f}"
        lines.append(f"• {q.name}: {v} ({q.pct:+.2f}%)")
    return "\n".join(lines)
