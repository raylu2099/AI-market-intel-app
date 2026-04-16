"""
A6: Unit tests for pure computation modules — no API calls.
Run: python -m pytest tests/ -v
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest


class TestStorage:
    def test_article_roundtrip(self):
        from intel.storage import Article, load_articles, save_articles

        a = Article(
            id="abc123",
            url="https://example.com/news",
            title="Test Article",
            publisher="example.com",
            date="2026-04-15",
            snippet="A test snippet.",
            body="Full body text here.",
            fetched=True,
            paywalled=False,
        )
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = Path(f.name)
        try:
            save_articles(path, [a])
            loaded = load_articles(path)
            assert len(loaded) == 1
            assert loaded[0].id == "abc123"
            assert loaded[0].title == "Test Article"
            assert loaded[0].body == "Full body text here."
            assert loaded[0].fetched is True
        finally:
            path.unlink(missing_ok=True)

    def test_dedupe(self):
        from intel.storage import Article, dedupe_articles

        a1 = Article(id="x", url="u1", title="T1", publisher="p", date="d", snippet="s")
        a2 = Article(id="x", url="u1", title="T1-dup", publisher="p", date="d", snippet="s")
        a3 = Article(id="y", url="u2", title="T2", publisher="p", date="d", snippet="s")
        result = dedupe_articles([a1, a2, a3])
        assert len(result) == 2
        assert result[0].title == "T1"  # first wins

    def test_make_id_deterministic(self):
        from intel.storage import Article

        id1 = Article.make_id("https://example.com/article")
        id2 = Article.make_id("https://example.com/article")
        id3 = Article.make_id("https://example.com/other")
        assert id1 == id2
        assert id1 != id3


class TestTechnicals:
    def test_rsi_calculation(self):
        from intel.technicals import _rsi
        import pandas as pd

        # Realistic zigzag: alternating up +2, down -1 → net uptrend with real losses
        moves = [100.0]
        for i in range(59):
            moves.append(moves[-1] + (2.0 if i % 2 == 0 else -1.0))
        prices = pd.Series(moves)
        rsi = _rsi(prices, 14)
        valid = rsi.dropna()
        assert len(valid) > 0, "RSI should have valid values for zigzag series"
        last_rsi = float(valid.iloc[-1])
        assert 0 <= last_rsi <= 100, f"RSI should be 0-100, got {last_rsi}"
        # Net uptrend → RSI should be > 50
        assert last_rsi > 50, f"Net uptrend RSI should be >50, got {last_rsi}"

    def test_sma(self):
        from intel.technicals import _sma
        import pandas as pd

        prices = pd.Series([10.0] * 50)
        sma = _sma(prices, 50)
        assert abs(float(sma.iloc[-1]) - 10.0) < 0.01


class TestRegime:
    def test_regime_classification_logic(self):
        """Test the classification logic directly (no yfinance)."""
        # Can't easily test compute_regime() without mocking yfinance,
        # but we can verify the dataclass works
        from intel.macro_regime import RegimeSnapshot

        snap = RegimeSnapshot(
            regime="GOLDILOCKS",
            growth_momentum=5.0,
            inflation_momentum=-2.0,
        )
        assert snap.regime == "GOLDILOCKS"
        assert snap.err == ""


class TestTelegram:
    def test_split_short(self):
        from intel.telegram import split_message

        result = split_message("short text")
        assert result == ["short text"]

    def test_split_long(self):
        from intel.telegram import split_message

        text = "para1\n\n" + "x" * 4000 + "\n\npara3"
        parts = split_message(text, limit=3500)
        assert len(parts) >= 2
        for p in parts:
            assert len(p) <= 3500


class TestUrgency:
    def test_banner_levels(self):
        from intel.urgency import urgency_banner, urgency_level

        assert urgency_banner(12.0) == ""
        assert "高波动" in urgency_banner(28.0)
        assert "极度恐慌" in urgency_banner(40.0)
        assert urgency_level(12.0) == "normal"
        assert urgency_level(28.0) == "high"
        assert urgency_level(40.0) == "panic"


class TestCostTracker:
    def test_record_and_get(self):
        from intel.cost_tracker import _DAILY_COSTS, record_cost, get_session_costs

        _DAILY_COSTS.clear()
        record_cost("test_a", 0.01)
        record_cost("test_a", 0.02)
        record_cost("test_b", 0.05)
        costs = get_session_costs()
        assert abs(costs["test_a"] - 0.03) < 1e-9
        assert abs(costs["test_b"] - 0.05) < 1e-9
        _DAILY_COSTS.clear()
