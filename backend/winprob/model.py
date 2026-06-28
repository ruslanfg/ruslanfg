"""Win/draw/loss probability for a single match.

One coherent model is used pre-match and in-match:

  * Map each team's Elo (+ optional home edge) to an expected-goals rate, nudged
    by recent form. Pre-match outcome = distribution of independent Poisson goal
    counts. In-match = current score + Poisson goals over the *remaining* time.
  * Outcome probabilities come from convolving the two goal distributions
    (a Skellam-style difference), so the draw probability emerges naturally.

Everything is computed from fetched inputs; nothing about the result is assumed.
The estimate ships with a confidence band that is wide while ratings are
provisional (few matches played) and narrows as real results accumulate.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .elo import expected_score

REGULATION_MINUTES = 90
_MAX_GOALS = 12


def _poisson_vector(lmbda: float) -> list[float]:
    """pmf over 0.._MAX_GOALS goals, normalized (tail truncated)."""
    lmbda = max(1e-6, lmbda)
    v = []
    p = math.exp(-lmbda)  # pmf(0)
    v.append(p)
    for k in range(1, _MAX_GOALS + 1):
        p = p * lmbda / k
        v.append(p)
    s = sum(v)
    return [x / s for x in v]


def _outcome_from_goal_dists(
    home_now: int, away_now: int, vh: list[float], va: list[float]
) -> tuple[float, float, float]:
    """P(home), P(draw), P(away) for final score = (now + extra) per side."""
    p_home = p_draw = p_away = 0.0
    for i, ph in enumerate(vh):
        fh = home_now + i
        for j, pa in enumerate(va):
            fa = away_now + j
            p = ph * pa
            if fh > fa:
                p_home += p
            elif fh == fa:
                p_draw += p
            else:
                p_away += p
    total = p_home + p_draw + p_away
    return p_home / total, p_draw / total, p_away / total


@dataclass
class ModelInputs:
    home_id: str
    home_name: str
    away_id: str
    away_name: str
    home_elo: Optional[float]
    away_elo: Optional[float]
    home_matches: int = 0
    away_matches: int = 0
    home_ppg: Optional[float] = None  # recent-form points per game (0..3)
    away_ppg: Optional[float] = None
    form_n: int = 0
    # live state (None => pre-match)
    minute: Optional[int] = None
    home_goals: Optional[int] = None
    away_goals: Optional[int] = None
    is_live: bool = False


def compute(inp: ModelInputs, cfg) -> Optional[dict]:
    """Return a ModelEstimate-shaped dict, or None if inputs are insufficient
    (e.g. no Elo for either side — we never invent a number)."""
    if inp.home_elo is None or inp.away_elo is None:
        return None

    m = cfg.model
    elo_diff = (inp.home_elo + m.home_field_advantage) - inp.away_elo

    # Elo edge -> goal supremacy, then split a baseline total into two rates.
    supremacy = m.goals_per_400_elo * (elo_diff / 400.0)
    if inp.home_ppg is not None and inp.away_ppg is not None:
        supremacy += m.form_weight * (inp.home_ppg - inp.away_ppg)

    half = m.avg_total_goals / 2.0
    lambda_home = max(0.12, half + supremacy / 2.0)
    lambda_away = max(0.12, half - supremacy / 2.0)

    # Remaining-time scaling for live matches.
    live = bool(inp.is_live and inp.minute is not None)
    if live:
        remaining = max(0.0, (REGULATION_MINUTES - min(inp.minute, REGULATION_MINUTES)) / REGULATION_MINUTES)
        gh = inp.home_goals or 0
        ga = inp.away_goals or 0
        vh = _poisson_vector(lambda_home * remaining)
        va = _poisson_vector(lambda_away * remaining)
        basis = "in-match"
    else:
        remaining = 1.0
        gh = ga = 0
        vh = _poisson_vector(lambda_home)
        va = _poisson_vector(lambda_away)
        basis = "pre-match"

    p_home, p_draw, p_away = _outcome_from_goal_dists(gh, ga, vh, va)

    # Confidence band: wide while ratings are provisional; narrower in-match.
    min_matches = min(inp.home_matches, inp.away_matches)
    band = min(0.22, 0.03 + 0.22 / (min_matches + 1))
    if live:
        band = band * (0.5 + 0.5 * remaining)
    provisional = min_matches < m.provisional_matches

    factors = [
        {
            "label": "Elo rating gap",
            "detail": (
                f"{inp.home_name} {inp.home_elo:.0f} vs {inp.away_name} {inp.away_elo:.0f} "
                f"(Δ {elo_diff:+.0f})"
            ),
        }
    ]
    if inp.home_ppg is not None and inp.away_ppg is not None and inp.form_n:
        factors.append(
            {
                "label": f"Recent form (last {inp.form_n})",
                "detail": (
                    f"{inp.home_name} {inp.home_ppg:.2f} vs {inp.away_name} "
                    f"{inp.away_ppg:.2f} pts/game"
                ),
            }
        )
    factors.append(
        {
            "label": "Model expected goals",
            "detail": f"{inp.home_name} {lambda_home:.2f} – {lambda_away:.2f} {inp.away_name}",
        }
    )
    if live:
        factors.append(
            {
                "label": "Live state",
                "detail": (
                    f"{gh}–{ga} at ~{inp.minute}′ "
                    f"(~{remaining * 100:.0f}% of regulation remaining)"
                ),
            }
        )

    return {
        "home_win": round(p_home, 4),
        "draw": round(p_draw, 4),
        "away_win": round(p_away, 4),
        "band": round(band, 4),
        "provisional": provisional,
        "basis": basis,
        "expected_goals": {"home": round(lambda_home, 2), "away": round(lambda_away, 2)},
        "factors": factors,
    }
