"""
U1: Tooltip definitions for financial indicators.
Used by Jinja2 templates to show contextual explanations on hover.
"""

TOOLTIPS = {
    # Technical
    "RSI": "14日相对强弱指数。>70=超买（可能回调），<30=超卖（可能反弹）",
    "SMA50": "50日简单移动平均线。价格在上方=短期趋势看多",
    "SMA200": "200日简单移动平均线。价格在上方=长期趋势看多",
    "金叉": "50日均线上穿200日均线 — 经典看多信号",
    "死叉": "50日均线下穿200日均线 — 经典看空信号",
    "多头排列": "50日 > 200日均线 — 上升趋势中",
    "空头排列": "50日 < 200日均线 — 下降趋势中",
    "Bollinger": "布林带：价格触及上轨=可能超买，触及下轨=可能超卖",
    "52w_high": "距离52周最高点的百分比。越接近0%=越接近历史高位",

    # Valuation
    "P/E": "市盈率 = 股价/每股收益。越高=越贵。科技股通常30-60x，金融10-20x",
    "forward_PE": "前瞻市盈率 = 股价/未来12个月预期EPS。比trailing P/E更前瞻",
    "P/S": "市销率 = 市值/年营收。高增长公司通常较高",
    "PEG": "市盈增长比 = P/E / 盈利增速。<1=被低估，>2=偏贵",

    # Earnings
    "EPS": "每股收益（稀释后）",
    "beat": "实际EPS超过分析师一致预期 — 利好",
    "miss": "实际EPS低于分析师一致预期 — 利空",
    "beat_rate": "过去4个季度中超过预期的比率。100%=每次都超预期",
    "YoY": "同比变化 = 与去年同期相比的增长率",

    # Macro
    "VIX": "恐慌指数。<15=低波动，15-25=正常，25-35=恐慌，>35=极度恐慌",
    "DXY": "美元指数。衡量美元对一篮子货币的强弱",
    "10Y": "10年期美国国债收益率。上升=市场预期通胀/加息",
    "USDCNY": "美元兑人民币汇率。上升=人民币贬值",
    "copper": "铜价常被称为'铜博士' — 经济健康的领先指标",
    "BTC": "比特币。常作为风险偏好的代理指标",

    # Regime
    "GOLDILOCKS": "增长向好 + 通胀温和：股票友好环境，成长股跑赢",
    "REFLATION": "增长向好 + 通胀上升：大宗商品和周期股受益",
    "STAGFLATION": "增长放缓 + 通胀上升：最危险regime，现金和黄金避险",
    "DEFLATION": "增长放缓 + 通胀下降：长债受益，风险资产承压",
    "contango": "VIX远月>近月 = 正常市场结构（目前不恐慌）",
    "backwardation": "VIX近月>远月 = 市场当前正在恐慌",

    # Sentiment
    "put_call": "看跌/看涨期权比。>1.2=市场偏空（反向看多），<0.7=偏多（反向看空）",
    "short_interest": "做空比例 = 被卖空的股数占流通股百分比。>10%=做空拥挤",
    "short_ratio": "空头回补天数 = 以当前成交量需几天才能回补所有空仓",
}


def tip(key: str) -> str:
    """Return tooltip text for a given key, or empty string."""
    return TOOLTIPS.get(key, "")
