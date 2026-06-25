"""Normalized domain models shared by the live and simulated data providers.

Keeping a single normalized shape means the engine, scorer and API never care
whether data came from the live Polymarket APIs or the offline simulator.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

UP = "UP"
DOWN = "DOWN"


@dataclass
class Market:
    """A single BTC 5-minute Up/Down binary market."""
    condition_id: str
    question: str
    slug: str
    up_token_id: str
    down_token_id: str
    start_time: int          # epoch seconds (window open)
    end_time: int            # epoch seconds (window close / resolution)
    neg_risk: bool = False
    active: bool = True
    closed: bool = False
    resolved_outcome: Optional[str] = None   # 'UP' | 'DOWN' | None
    source: str = "live"
    raw: Optional[dict[str, Any]] = None

    def token_for(self, outcome: str) -> str:
        return self.up_token_id if outcome == UP else self.down_token_id

    def outcome_for_token(self, token_id: str) -> Optional[str]:
        if token_id == self.up_token_id:
            return UP
        if token_id == self.down_token_id:
            return DOWN
        return None

    def as_db(self) -> dict[str, Any]:
        return {
            "condition_id": self.condition_id,
            "question": self.question,
            "slug": self.slug,
            "up_token_id": self.up_token_id,
            "down_token_id": self.down_token_id,
            "neg_risk": int(self.neg_risk),
            "start_time": self.start_time,
            "end_time": self.end_time,
            "active": int(self.active),
            "closed": int(self.closed),
            "resolved_outcome": self.resolved_outcome,
            "resolved_at": None,
            "source": self.source,
            "raw": self.raw,
        }


@dataclass
class Quote:
    """Top-of-book for a single outcome token."""
    token_id: str
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None

    @property
    def mid(self) -> Optional[float]:
        if self.best_bid is not None and self.best_ask is not None:
            return (self.best_bid + self.best_ask) / 2
        return self.best_bid if self.best_bid is not None else self.best_ask


@dataclass
class ObservedTrade:
    """A real trade by a tracked wallet (from Data API or on-chain logs)."""
    wallet: str
    condition_id: Optional[str]
    token_id: Optional[str]
    outcome: Optional[str]    # 'UP' | 'DOWN'
    side: str                 # 'BUY' | 'SELL'
    price: float
    size: float               # shares
    timestamp: int
    tx_hash: Optional[str] = None
    source: str = "data_api"

    @property
    def usd(self) -> float:
        return float(self.price) * float(self.size)

    def as_db(self) -> dict[str, Any]:
        return {
            "wallet": self.wallet,
            "condition_id": self.condition_id,
            "token_id": self.token_id,
            "outcome": self.outcome,
            "side": self.side,
            "price": self.price,
            "size": self.size,
            "usd": self.usd,
            "timestamp": self.timestamp,
            "tx_hash": self.tx_hash,
            "source": self.source,
        }


@dataclass
class WalletScore:
    wallet: str
    trades_count: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    realized_pnl: float = 0.0
    volume: float = 0.0
    vw_pnl: float = 0.0
    score: float = 0.0
    rank: Optional[int] = None
    lookback_days: Optional[int] = None
    first_seen: Optional[int] = None
    last_seen: Optional[int] = None


@dataclass
class SourceStatus:
    name: str
    ok: bool
    detail: str = ""
    error: str = ""
    sample: Any = field(default=None)
