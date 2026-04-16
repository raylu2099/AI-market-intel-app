"""
weekly_review slot: runs Friday afternoon, reviews the week's analysis
accuracy and provides a P&L-style retrospective of past calls.

Pipeline:
  1. Load all analyses from this week (Mon-Fri)
  2. Load current prices for any tickers mentioned in position theses
  3. Ask Claude to compare past calls against actual outcomes
  4. Archive the review
  5. Push to Telegram
"""
from __future__ import annotations

from datetime import timedelta

from ..claude_analyst import analyze
from ..config import Config
from ..cost_tracker import format_weekly_cost_summary
from ..pnl_tracker import load_all_positions, compute_pnl, format_pnl_review
from ..storage import load_recent_analyses, save_analysis
from ..telegram import split_message
from ..timeutil import now_pt, today_str
from .base import SlotResult


CATEGORY = "weekly_review"
SLOT_NAME = "weekly_review"

SYSTEM_PROMPT = """\
你是一位负责周回顾的市场分析师。你的任务是审视自己本周（周一到周五）的所有分析和仓位建议，对照实际市场走势做一次诚实的复盘。

## 输出要求（简体中文，Telegram HTML 格式）

### 1. 📊 本周判断回顾
对本周你做过的每个仓位主张，逐条评估：
- 当时的方向性判断是否正确
- 标的实际走势（如果你有价格数据）
- 你的逻辑是否成立，还是因为「错误原因的正确方向」
- 置信度标记当时是否准确

### 2. 🔍 模式识别
本周的事件里，你识别出哪些反复出现的模式？哪些主题在加速？

### 3. 🛠 改进建议
对你自己的分析方法、信源选择、或思维框架，有什么调整建议？

### 4. 📈 下周展望
基于本周的积累，下周最需要关注的 3 件事是什么？

## 规则
- 全部简体中文。专有名词保留英文。
- 诚实评估，不回避错误。
- 如果没有足够数据追溯结果，明确说明。
- 使用 `<b>` 标签做标题，`━━━━━━━━━━` 分隔章节。
"""


def run(cfg: Config) -> SlotResult:
    date_str = today_str(cfg.market_tz)

    # Load this week's analyses from both china and market_close
    china_analyses = load_recent_analyses(cfg, "china", 7)
    close_analyses = load_recent_analyses(cfg, "market_close", 7)

    all_analyses = []
    for date, content in china_analyses:
        all_analyses.append(f"## China Brief — {date}\n\n{content}")
    for date, content in close_analyses:
        all_analyses.append(f"## US Close — {date}\n\n{content}")

    if not all_analyses:
        return SlotResult(
            slot=SLOT_NAME,
            category=CATEGORY,
            date_str=date_str,
            articles=[],
            messages=["📋 <b>周回顾</b>\n\n本周尚无分析记录，跳过周回顾。"],
        )

    user_prompt = (
        f"# 今天日期：{now_pt().strftime('%Y-%m-%d %A')}\n\n"
        f"# 本周分析记录 ({len(all_analyses)} 份)\n\n"
        + "\n\n━━━━━━━━━━\n\n".join(all_analyses)
        + "\n\n---\n\n请生成本周回顾，严格按系统提示词格式输出。"
    )

    analysis_md = analyze(cfg, SYSTEM_PROMPT, user_prompt)
    save_analysis(cfg, CATEGORY, date_str, analysis_md)

    # Q12: P&L tracking
    positions = load_all_positions(cfg, days=7)
    positions = compute_pnl(positions)
    pnl_section = format_pnl_review(positions)

    # P6: Append weekly cost summary
    cost_summary = format_weekly_cost_summary(cfg)

    header = f"📋 <b>周回顾</b> — {now_pt():%a %m/%d}"
    full = (
        f"{header}\n\n{analysis_md}\n\n"
        f"━━━━━━━━━━\n{pnl_section}\n\n"
        f"━━━━━━━━━━\n{cost_summary}"
    )
    messages = split_message(full)

    return SlotResult(
        slot=SLOT_NAME,
        category=CATEGORY,
        date_str=date_str,
        articles=[],
        messages=messages,
        analysis_md=analysis_md,
    )
