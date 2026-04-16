"""Time zone and market-calendar helpers."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


BEIJING = ZoneInfo("Asia/Shanghai")
US_EASTERN = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


def now_utc() -> datetime:
    return datetime.now(tz=UTC)


def now_in(tz: ZoneInfo) -> datetime:
    return datetime.now(tz=tz)


def now_pt() -> datetime:
    return now_in(ZoneInfo("US/Pacific"))


def now_bj() -> datetime:
    return now_in(BEIJING)


def is_weekday(tz: ZoneInfo) -> bool:
    return now_in(tz).weekday() < 5


def today_str(tz: ZoneInfo) -> str:
    return now_in(tz).strftime("%Y-%m-%d")


def days_back(tz: ZoneInfo, n: int) -> list[str]:
    """Return the last n dates (inclusive of today) as YYYY-MM-DD strings."""
    today = now_in(tz).date()
    return [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)]
