"""Configuration loading.

Single source of truth is ``config.yaml`` (all tunables). Secrets are referenced
with ``${ENV_VAR}`` placeholders and resolved from the environment / ``.env``.

Usage::

    from bot.config import load_config
    cfg = load_config()                 # reads ./config.yaml + ./.env
    cfg.engine.starting_bankroll        # typed access
"""
from __future__ import annotations

import os
import re
import typing
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


# --------------------------------------------------------------------------- #
# Typed config sections
# --------------------------------------------------------------------------- #
@dataclass
class DataConfig:
    mode: str = "auto"  # live | sim | auto
    gamma_base_url: str = "https://gamma-api.polymarket.com"
    clob_base_url: str = "https://clob.polymarket.com"
    data_api_base_url: str = "https://data-api.polymarket.com"
    ws_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/"
    polygon_rpc_url: str = ""
    enable_onchain: bool = False
    poll_interval_seconds: float = 5.0
    http_timeout_seconds: float = 12.0
    max_retries: int = 3
    retry_backoff_seconds: float = 1.0


@dataclass
class MarketConfig:
    asset_symbol: str = "BTC"
    series_slugs: list[str] = field(default_factory=lambda: ["bitcoin-up-or-down"])
    question_contains: list[str] = field(default_factory=lambda: ["bitcoin up or down"])
    duration_minutes: int = 5


@dataclass
class ScoringConfig:
    win_rate_weight: float = 0.5
    pnl_weight: float = 0.4
    volume_weight: float = 0.1
    win_rate_exponent: float = 1.0


@dataclass
class WalletsConfig:
    lookback_days: int = 7
    min_trades: int = 15
    top_n: int = 40
    refresh_interval_seconds: float = 300.0
    max_wallets_tracked: int = 200
    backfill_windows: int = 180
    scoring: ScoringConfig = field(default_factory=ScoringConfig)


@dataclass
class EngineConfig:
    starting_bankroll: float = 1000.0
    bankroll_fraction: float = 0.10
    slippage_bps: float = 50.0
    min_position_usd: float = 1.0
    max_open_positions: int = 50
    max_position_usd: float = 500.0
    mirror_sells: bool = False


@dataclass
class SimConfig:
    seed: int = 1337
    num_wallets: int = 40
    btc_start_price: float = 65000.0
    btc_volatility_bps: float = 8.0
    wallet_trade_rate: float = 0.35
    accelerate: bool = True
    accelerated_window_seconds: int = 60


@dataclass
class ApiConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173"])
    ws_broadcast_interval_seconds: float = 2.0


@dataclass
class StorageConfig:
    db_path: str = "data/paper_trading.db"


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "logs/bot.log"
    json: bool = False


@dataclass
class Config:
    data: DataConfig = field(default_factory=DataConfig)
    market: MarketConfig = field(default_factory=MarketConfig)
    wallets: WalletsConfig = field(default_factory=WalletsConfig)
    engine: EngineConfig = field(default_factory=EngineConfig)
    sim: SimConfig = field(default_factory=SimConfig)
    api: ApiConfig = field(default_factory=ApiConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # Resolved absolute paths (populated by load_config)
    config_path: str = ""
    project_root: str = ""


# --------------------------------------------------------------------------- #
# Loader
# --------------------------------------------------------------------------- #
def _substitute_env(value: Any) -> Any:
    """Recursively replace ``${VAR}`` placeholders with environment values."""
    if isinstance(value, str):
        def repl(match: re.Match[str]) -> str:
            return os.environ.get(match.group(1), "")
        return _ENV_PATTERN.sub(repl, value)
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    return value


def _build(cls: type, data: dict[str, Any]) -> Any:
    """Construct a (possibly nested) dataclass from a dict, ignoring unknown keys."""
    if not is_dataclass(cls):
        return data
    kwargs: dict[str, Any] = {}
    # Resolve string annotations (PEP 563 / `from __future__ import annotations`).
    type_hints = typing.get_type_hints(cls)
    for f in fields(cls):
        if f.name not in data:
            continue
        raw = data[f.name]
        ftype = type_hints.get(f.name, f.type)
        if is_dataclass(ftype) and isinstance(raw, dict):
            kwargs[f.name] = _build(ftype, raw)
        else:
            kwargs[f.name] = raw
    return cls(**kwargs)


def find_project_root(start: Path | None = None) -> Path:
    """Walk upward to find the directory containing config.yaml."""
    start = (start or Path.cwd()).resolve()
    for candidate in [start, *start.parents]:
        if (candidate / "config.yaml").exists():
            return candidate
    return start


def load_config(path: str | os.PathLike | None = None) -> Config:
    """Load configuration from config.yaml + .env.

    Resolution order for the config file:
      1. explicit ``path`` argument
      2. ``$BOT_CONFIG`` environment variable
      3. ``config.yaml`` discovered by walking up from the cwd
    """
    root = find_project_root()
    # Load .env from the project root (does not override real env vars).
    load_dotenv(root / ".env", override=False)

    if path is None:
        path = os.environ.get("BOT_CONFIG")
    cfg_path = Path(path) if path else (root / "config.yaml")
    if not cfg_path.exists():
        raise FileNotFoundError(f"config.yaml not found at {cfg_path}")

    raw = yaml.safe_load(cfg_path.read_text()) or {}
    raw = _substitute_env(raw)

    cfg = _build(Config, raw)
    cfg.config_path = str(cfg_path.resolve())
    cfg.project_root = str(root)

    # Allow DB_PATH env override (handy for tests / multiple instances).
    if os.environ.get("DB_PATH"):
        cfg.storage.db_path = os.environ["DB_PATH"]

    # Normalize the db path & log file to absolute under project root.
    if not os.path.isabs(cfg.storage.db_path):
        cfg.storage.db_path = str(root / cfg.storage.db_path)
    if cfg.logging.file and not os.path.isabs(cfg.logging.file):
        cfg.logging.file = str(root / cfg.logging.file)

    return cfg


__all__ = ["Config", "load_config", "find_project_root"]
