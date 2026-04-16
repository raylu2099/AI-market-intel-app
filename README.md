# AI Market Intel App

A self-hosted market intelligence platform with **web dashboard** and automated Telegram briefings. Powered by Claude AI analysis + Perplexity web search + real-time financial data.

<p align="center">
  <strong>🌐 Web Dashboard</strong> &bull; <strong>🤖 Claude AI Analysis</strong> &bull; <strong>📊 Real-time Data</strong> &bull; <strong>📱 Telegram Push</strong>
</p>

## What is this?

A personal Bloomberg terminal alternative that:

1. **Searches** global news via Perplexity (English sources, Chinese output)
2. **Archives** every article to a local corpus (JSONL, searchable)
3. **Analyzes** with Claude AI in three voices:
   - 📝 Macro narrative (FT/Bloomberg editorial style)
   - 💹 Position thesis (Bridgewater-style with sizing + risk weights)
   - 🎯 Strategic intel (pure geopolitical, no investment view)
4. **Validates** all positions against quantitative data:
   - Technical indicators (SMA, RSI, Bollinger Bands)
   - Valuations (P/E, forward P/E, PEG, analyst targets)
   - Earnings (actual vs consensus, beat rate, insider activity)
   - Macro regime (growth×inflation quadrant)
   - Sentiment (VIX term structure, put/call ratio, short interest)
   - CFTC institutional positioning
5. **Pushes** to Telegram + displays on **web dashboard**
6. **Learns** — 30-day rolling memory of past analyses + P&L tracking

## Web Dashboard

```bash
# Quick start with Docker
docker compose up -d
open http://localhost:8501
```

Pages:
- **Dashboard** — Live market snapshot: watchlist, macro, sector radar, regime classification
- **Stocks** — Deep dive per ticker: technicals + valuations + earnings + short interest
- **History** — Browse past analyses (China brief, US close, weekly review)
- **API** — `POST /api/run/<slot>` to trigger analysis, `GET /api/status` for health

## Automated Briefings (Cron)

| Slot | Time (PT) | Type | Content |
|------|-----------|------|---------|
| `stocks_pre` | 05:30 | Light | Per-stock pre-market news |
| `premarket` | 06:00 | Light | Market overview + technicals + sentiment + events |
| `open` | 06:30 | Light | Opening headlines |
| `midday` | 09:30 | Light | Mid-session flow |
| `close` | 13:00 | **Deep** | Full Claude 3-persona US close analysis |
| `stocks_post` | 13:30 | Light | Per-stock post-close news |
| `china_open` | 18:30 | **Deep** | Full Claude 3-persona China intelligence brief |
| `weekly_review` | Fri 14:00 | **Deep** | Week retrospective + P&L tracking |
| `watchdog` | */15 min | Alert | Breaking news detection |

## Data Stack

| Layer | Source | Cost |
|-------|--------|------|
| News search | Perplexity sonar | ~$3-5/mo |
| Article fetch | trafilatura (free) | $0 |
| Prices + technicals | yfinance (free) | $0 |
| Earnings + insider | Financial Datasets API | varies |
| Sentiment | yfinance options + VIX | $0 |
| CFTC positioning | CFTC.gov (free CSV) | $0 |
| AI analysis | Claude (Max subscription or API) | subscription or ~$10/mo |
| Delivery | Telegram Bot API (free) | $0 |

## Setup

```bash
# 1. Clone
git clone https://github.com/raylu2099/AI-market-intel-app.git
cd AI-market-intel-app

# 2. Setup
./setup.sh                          # creates venv, installs deps

# 3. Configure
cp .env.example .env
$EDITOR .env                        # add your API keys

# 4. Health check
./bin/doctor.sh

# 5a. Web dashboard
uvicorn app.main:app --port 8000

# 5b. OR with Docker
docker compose up -d

# 6. Install cron for automated briefings
sudo bash ./bin/install-cron.sh     # Synology
# OR
bash ./bin/install-cron.sh          # standard Linux
```

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     Web Dashboard                        │
│  FastAPI + Jinja2 + TailwindCSS (no build step)         │
│  Dashboard / Stocks / History / API                      │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────┴─────────────────────────────────┐
│                    Core Engine                            │
│  intel/ — search, fetch, analyze, archive, push          │
├──────────────────────────────────────────────────────────┤
│  Data Sources:                                           │
│  Perplexity | yfinance | Financial Datasets | CFTC       │
│  trafilatura | Google News RSS (fallback)                │
├──────────────────────────────────────────────────────────┤
│  AI Analysis:                                            │
│  Claude (claude -p CLI or Anthropic API)                 │
│  3-persona output + quantitative validation              │
├──────────────────────────────────────────────────────────┤
│  Delivery:                                               │
│  Telegram Bot | Web Dashboard | data/ archive            │
└──────────────────────────────────────────────────────────┘
```

## CLI-Only Version

If you don't need the web dashboard, use the lighter
[AI-market-intel](https://github.com/raylu2099/AI-market-intel) repo
(same engine, no FastAPI/web dependencies).

## License

MIT. See [LICENSE](LICENSE).
