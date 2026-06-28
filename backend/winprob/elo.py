"""Elo ratings, World-Football-Elo style.

Ratings are *not* hardcoded. They are built at runtime by replaying the real
FINISHED matches we fetch from the football data API, in chronological order,
starting every team from a neutral provisional base (1500). With ~2-3 weeks of
the tournament played, this yields meaningful, fully-explainable ratings; before
that, ratings stay near the base and the model reports a wide confidence band.

Reference: the goal-difference multiplier follows the well-documented
World Football Elo Ratings update (eloratings.net).
"""
from __future__ import annotations

from dataclasses import dataclass


def expected_score(rating_a: float, rating_b: float, hfa: float = 0.0) -> float:
    """Elo win expectancy for A vs B (draw counts as half), in [0, 1]."""
    return 1.0 / (1.0 + 10 ** (-((rating_a + hfa) - rating_b) / 400.0))


def goal_difference_multiplier(goal_diff: int) -> float:
    """Importance multiplier on K for the margin of victory."""
    gd = abs(goal_diff)
    if gd <= 1:
        return 1.0
    if gd == 2:
        return 1.5
    return (11 + gd) / 8.0


@dataclass
class _Rating:
    name: str
    rating: float
    matches: int


class EloModel:
    def __init__(self, k_factor: float = 40.0, base_rating: float = 1500.0, hfa: float = 0.0):
        self.k = k_factor
        self.base = base_rating
        self.hfa = hfa
        self._r: dict[str, _Rating] = {}

    def _team(self, team_id: str, name: str) -> _Rating:
        r = self._r.get(team_id)
        if r is None:
            r = _Rating(name=name, rating=self.base, matches=0)
            self._r[team_id] = r
        elif name and r.name != name:
            r.name = name
        return r

    def update(
        self,
        home_id: str,
        home_name: str,
        away_id: str,
        away_name: str,
        home_goals: int,
        away_goals: int,
        *,
        neutral: bool = True,
    ) -> None:
        """Apply one finished match to the ratings."""
        home = self._team(home_id, home_name)
        away = self._team(away_id, away_name)
        hfa = 0.0 if neutral else self.hfa

        exp_home = expected_score(home.rating, away.rating, hfa)
        if home_goals > away_goals:
            score_home = 1.0
        elif home_goals < away_goals:
            score_home = 0.0
        else:
            score_home = 0.5

        mult = goal_difference_multiplier(home_goals - away_goals)
        delta = self.k * mult * (score_home - exp_home)
        home.rating += delta
        away.rating -= delta
        home.matches += 1
        away.matches += 1

    def ratings(self) -> dict[str, dict]:
        return {
            tid: {"name": r.name, "rating": round(r.rating, 2), "matches": r.matches}
            for tid, r in self._r.items()
        }

    def get(self, team_id: str) -> dict | None:
        r = self._r.get(team_id)
        if r is None:
            return None
        return {"name": r.name, "rating": round(r.rating, 2), "matches": r.matches}


def build_ratings(finished_matches: list[dict], k_factor: float, base_rating: float, hfa: float) -> EloModel:
    """Replay finished matches (each: home_id/home_name/away_id/away_name/
    home_goals/away_goals/utc_date) in date order to produce ratings."""
    model = EloModel(k_factor=k_factor, base_rating=base_rating, hfa=hfa)
    ordered = sorted(finished_matches, key=lambda m: m.get("utc_date") or "")
    for m in ordered:
        if m.get("home_goals") is None or m.get("away_goals") is None:
            continue
        if not m.get("home_id") or not m.get("away_id"):
            continue
        model.update(
            str(m["home_id"]),
            m.get("home_name", ""),
            str(m["away_id"]),
            m.get("away_name", ""),
            int(m["home_goals"]),
            int(m["away_goals"]),
            neutral=bool(m.get("neutral", True)),
        )
    return model
