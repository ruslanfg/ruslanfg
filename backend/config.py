"""Runtime configuration.

Secrets and machine-specific values come from the environment / ``.env`` (loaded
once here). Everything else has a sensible default that an env var can override.
Nothing about the tournament itself is configured here — all match data is
fetched live at runtime.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the repo root (next to this package), if present.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _env(name: str, default: str = "") -> str:
    val = os.getenv(name)
    return val if val is not None and val != "" else default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(_env(name, str(default))))
    except ValueError:
        return default


@dataclass(frozen=True)
class FootballConfig:
    api_key: str = field(default_factory=lambda: _env("FOOTBALL_DATA_API_KEY"))
    base_url: str = field(
        default_factory=lambda: _env("FOOTBALL_DATA_BASE_URL", "https://api.football-data.org/v4")
    )
    competition: str = field(default_factory=lambda: _env("FOOTBALL_WC_COMPETITION", "WC"))

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


@dataclass(frozen=True)
class OddsConfig:
    api_key: str = field(default_factory=lambda: _env("THE_ODDS_API_KEY"))
    base_url: str = field(
        default_factory=lambda: _env("THE_ODDS_API_BASE_URL", "https://api.the-odds-api.com/v4")
    )
    sport_key: str = field(default_factory=lambda: _env("ODDS_SPORT_KEY", "soccer_fifa_world_cup"))
    regions: str = field(default_factory=lambda: _env("ODDS_REGIONS", "us,uk,eu"))

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


@dataclass(frozen=True)
class PolymarketConfig:
    gamma_url: str = field(
        default_factory=lambda: _env("POLYMARKET_GAMMA_URL", "https://gamma-api.polymarket.com")
    )
    data_url: str = field(
        default_factory=lambda: _env("POLYMARKET_DATA_URL", "https://data-api.polymarket.com")
    )
    leaderboard_url: str = field(
        default_factory=lambda: _env("POLYMARKET_LEADERBOARD_URL", "https://lb-api.polymarket.com")
    )
    wc_query: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            q.strip().lower()
            for q in _env("POLYMARKET_WC_QUERY", "world cup,fifa").split(",")
            if q.strip()
        )
    )
    # Polymarket is always reachable in principle (no key needed); "configured"
    # is True so we attempt it and degrade gracefully if egress is blocked.
    configured: bool = True


@dataclass(frozen=True)
class ModelConfig:
    # World-Football-Elo style parameters.
    k_factor: float = field(default_factory=lambda: _env_float("ELO_K_FACTOR", 40.0))
    base_rating: float = 1500.0
    # Home-field advantage in Elo points. The 2026 WC is largely neutral-venue,
    # so this defaults to 0; hosts' advantage is not assumed.
    home_field_advantage: float = field(default_factory=lambda: _env_float("ELO_HFA", 0.0))
    # Average total goals per match used to anchor the Poisson scoring model.
    avg_total_goals: float = field(default_factory=lambda: _env_float("MODEL_AVG_GOALS", 2.6))
    # How strongly an Elo edge maps to a goal-supremacy edge.
    goals_per_400_elo: float = field(default_factory=lambda: _env_float("MODEL_GOALS_PER_400", 1.0))
    # Weight of recent-form differential nudging the Elo expectation (0..1).
    form_weight: float = field(default_factory=lambda: _env_float("MODEL_FORM_WEIGHT", 0.10))
    # Matches behind a rating before it stops being "provisional" (wide band).
    provisional_matches: int = field(default_factory=lambda: _env_int("MODEL_PROVISIONAL_MATCHES", 5))


@dataclass(frozen=True)
class Config:
    football: FootballConfig = field(default_factory=FootballConfig)
    odds: OddsConfig = field(default_factory=OddsConfig)
    polymarket: PolymarketConfig = field(default_factory=PolymarketConfig)
    model: ModelConfig = field(default_factory=ModelConfig)

    db_path: str = field(default_factory=lambda: _env("DB_PATH", "data/worldcup.db"))
    refresh_live_seconds: int = field(default_factory=lambda: _env_int("REFRESH_LIVE_SECONDS", 60))
    refresh_baseline_seconds: int = field(
        default_factory=lambda: _env_int("REFRESH_BASELINE_SECONDS", 6 * 60 * 60)
    )
    value_edge_threshold: float = field(
        default_factory=lambda: _env_float("VALUE_EDGE_THRESHOLD", 0.05)
    )
    http_timeout_seconds: float = field(
        default_factory=lambda: _env_float("HTTP_TIMEOUT_SECONDS", 15.0)
    )
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip()
            for o in _env("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
            if o.strip()
        )
    )
    host: str = field(default_factory=lambda: _env("HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env_int("PORT", 8000))


_config: Config | None = None


def get_config() -> Config:
    """Return the process-wide config singleton."""
    global _config
    if _config is None:
        _config = Config()
    return _config
