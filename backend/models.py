"""Pydantic models describing the dashboard API contract.

The service layer builds a :class:`DashboardSnapshot`; the API serves its
``model_dump()``. Keeping the shape here makes the frontend/back contract
explicit and validated.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

DISCLAIMER = (
    "Outputs are statistical model estimates and public betting-market data, shown "
    "for information only. They are NOT betting advice, financial advice, or "
    "guaranteed outcomes. Probabilities are uncertain estimates with confidence bands."
)


class SourceStatus(BaseModel):
    name: str
    label: str
    ok: bool
    detail: Optional[str] = None
    last_ok_at: Optional[int] = None
    checked_at: Optional[int] = None


class TeamRef(BaseModel):
    id: Optional[str] = None
    name: str
    crest: Optional[str] = None
    elo: Optional[float] = None
    elo_provisional: bool = False
    # Recent form as a list of "W"/"D"/"L" (most recent last) plus points-per-game.
    form: Optional[list[str]] = None
    form_ppg: Optional[float] = None


class Score(BaseModel):
    home: Optional[int] = None
    away: Optional[int] = None


class Factor(BaseModel):
    label: str
    detail: str


class ExpectedGoals(BaseModel):
    home: float
    away: float


class ModelEstimate(BaseModel):
    home_win: float
    draw: float
    away_win: float
    # Half-width of the confidence band applied to each probability (0..1).
    band: float
    provisional: bool
    basis: Literal["pre-match", "in-match"]
    expected_goals: ExpectedGoals
    factors: list[Factor]
    note: str = "Model estimate, not a guarantee."


class ValueFlag(BaseModel):
    # model_pct - market_pct (positive = model sees more value than the book)
    edge: Optional[float] = None
    flagged: bool = False


class OutcomeRow(BaseModel):
    key: Literal["home", "draw", "away"]
    label: str
    model_pct: Optional[float] = None
    sportsbook_pct: Optional[float] = None
    polymarket_pct: Optional[float] = None
    value: ValueFlag = Field(default_factory=ValueFlag)


class MarketComparison(BaseModel):
    outcomes: list[OutcomeRow]
    sportsbook_available: bool = False
    sportsbook_book: Optional[str] = None
    polymarket_available: bool = False
    polymarket_slug: Optional[str] = None
    note: Optional[str] = None


class Lineups(BaseModel):
    home: list[str] = Field(default_factory=list)
    away: list[str] = Field(default_factory=list)
    formation_home: Optional[str] = None
    formation_away: Optional[str] = None


class MatchCard(BaseModel):
    id: str
    status: Literal["upcoming", "live", "finished", "unknown"]
    utc_date: Optional[str] = None
    minute: Optional[int] = None
    minute_approx: bool = True
    stage: Optional[str] = None
    group: Optional[str] = None
    home: TeamRef
    away: TeamRef
    score: Score = Field(default_factory=Score)
    model: Optional[ModelEstimate] = None
    market: Optional[MarketComparison] = None
    lineups_available: bool = False
    lineups: Optional[Lineups] = None
    data_note: Optional[str] = None


class TraderPosition(BaseModel):
    market_title: str
    slug: Optional[str] = None
    outcome: Optional[str] = None
    size: Optional[float] = None  # shares held
    avg_price: Optional[float] = None
    cur_price: Optional[float] = None
    value_usd: Optional[float] = None
    unrealized_pnl: Optional[float] = None


class Trader(BaseModel):
    rank: Optional[int] = None
    address: str
    display: Optional[str] = None
    pnl: Optional[float] = None
    volume: Optional[float] = None
    # None  -> positions could not be fetched (unavailable)
    # []    -> fetched successfully, trader holds no current WC position
    positions: Optional[list[TraderPosition]] = None
    positions_note: Optional[str] = None


class SmartMoney(BaseModel):
    available: bool = False
    note: Optional[str] = None
    leaderboard: list[Trader] = Field(default_factory=list)


class DashboardSnapshot(BaseModel):
    updated_at: int
    disclaimer: str = DISCLAIMER
    tournament: dict = Field(
        default_factory=lambda: {
            "name": "FIFA World Cup 2026",
            "hosts": "USA · Canada · Mexico",
            "window": "Jun 11 – Jul 19, 2026",
        }
    )
    sources: list[SourceStatus] = Field(default_factory=list)
    matches: list[MatchCard] = Field(default_factory=list)
    smart_money: SmartMoney = Field(default_factory=SmartMoney)
    live_count: int = 0
    value_count: int = 0
