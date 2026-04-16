"""
Configuration loader. Reads .env, exposes typed config and resolved paths.

All paths are derived relative to the project root unless overridden by env
vars, so the project can be cloned to any host without editing code.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_env_file(PROJECT_ROOT / ".env")


def _load_named_config(name: str | None) -> None:
    """Load a named config file (configs/<name>.env) for multi-instance."""
    if not name:
        return
    p = PROJECT_ROOT / "configs" / f"{name}.env"
    if p.exists():
        for ln in p.read_text().splitlines():
            if "=" in ln and not ln.strip().startswith("#"):
                k, _, v = ln.partition("=")
                os.environ[k.strip()] = v.strip().strip('"').strip("'")


def _env(key: str, default: str | None = None, required: bool = False) -> str:
    val = os.environ.get(key, default)
    if required and not val:
        raise RuntimeError(
            f"Required env var {key} is not set. "
            f"Add it to {PROJECT_ROOT / '.env'} (see .env.example)."
        )
    return val or ""


def _parse_watchlist(raw: str) -> list[tuple[str, str]]:
    out = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            t, n = item.split(":", 1)
            out.append((t.strip().upper(), n.strip()))
        else:
            out.append((item.upper(), item.upper()))
    return out


@dataclass(frozen=True)
class Config:
    # Secrets
    perplexity_api_key: str
    telegram_bot_token: str
    telegram_chat_id: str

    # Claude runner
    claude_runner: str          # "cli" or "api"
    claude_model: str
    anthropic_api_key: str

    # Paths
    data_dir: Path
    logs_dir: Path
    prompts_dir: Path

    # Market
    watchlist: list[tuple[str, str]]
    market_tz: ZoneInfo

    # Perplexity
    pplx_model_search: str
    pplx_model_analysis: str
    pplx_search_context: str

    # History
    history_window_days: int

    # Derived
    project_root: Path = field(default=PROJECT_ROOT)

    @property
    def utc(self) -> timezone:
        return timezone.utc

    def sources_dir(self, category: str, subcat: str = "") -> Path:
        p = self.data_dir / "sources" / category
        if subcat:
            p = p / subcat
        return p

    def analyses_dir(self, category: str) -> Path:
        return self.data_dir / "analyses" / category

    def pushes_dir(self, date_str: str) -> Path:
        return self.data_dir / "pushes" / date_str


def load_config(config_name: str | None = None) -> Config:
    _load_named_config(config_name)
    data_dir = Path(_env("MARKET_INTEL_DATA_DIR", str(PROJECT_ROOT / "data")))
    logs_dir = Path(_env("MARKET_INTEL_LOGS_DIR", str(PROJECT_ROOT / "logs")))
    prompts_dir = PROJECT_ROOT / "prompts"

    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    return Config(
        perplexity_api_key=_env("PERPLEXITY_API_KEY", required=True),
        telegram_bot_token=_env("TELEGRAM_BOT_TOKEN", required=True),
        telegram_chat_id=_env("TELEGRAM_CHAT_ID", required=True),
        claude_runner=_env("CLAUDE_RUNNER", "cli"),
        claude_model=_env("CLAUDE_MODEL", "claude-sonnet-4-6"),
        anthropic_api_key=_env("ANTHROPIC_API_KEY", ""),
        data_dir=data_dir,
        logs_dir=logs_dir,
        prompts_dir=prompts_dir,
        watchlist=_parse_watchlist(
            _env("WATCHLIST", "META:Meta,GOOGL:Google,NVDA:Nvidia,TSLA:Tesla,NVO:Novo Nordisk")
        ),
        market_tz=ZoneInfo(_env("MARKET_TZ", "US/Pacific")),
        pplx_model_search=_env("PPLX_MODEL_SEARCH", "sonar"),
        pplx_model_analysis=_env("PPLX_MODEL_ANALYSIS", "sonar-pro"),
        pplx_search_context=_env("PPLX_SEARCH_CONTEXT", "high"),
        history_window_days=int(_env("HISTORY_WINDOW_DAYS", "30")),
    )
