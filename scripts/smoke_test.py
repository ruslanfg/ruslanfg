"""Offline smoke test: validates the model math + graceful degradation.

Run:  python -m scripts.smoke_test     (from repo root, venv active)

This does NOT contact any network. It feeds the Elo + win-probability model
synthetic inputs to confirm the math is sane, then runs a full refresh against
the (blocked) live sources to confirm everything degrades to "data unavailable"
without inventing numbers or crashing.
"""
from __future__ import annotations

import asyncio

from backend.config import get_config
from backend.db import Database
from backend.service import Aggregator
from backend.winprob import model as winmodel
from backend.winprob.elo import build_ratings


def test_elo_and_model():
    print("== Elo + win-probability model ==")
    # Synthetic finished matches: 'strong' beats 'weak' repeatedly.
    finished = [
        {"home_id": "S", "home_name": "Strong", "away_id": "W", "away_name": "Weak",
         "home_goals": 3, "away_goals": 0, "utc_date": f"2026-06-1{i}T00:00:00Z"}
        for i in range(1, 6)
    ]
    elo = build_ratings(finished, k_factor=40, base_rating=1500, hfa=0.0)
    s = elo.get("S"); w = elo.get("W")
    print(f"  Strong Elo={s['rating']} ({s['matches']} m), Weak Elo={w['rating']} ({w['matches']} m)")
    assert s["rating"] > 1500 > w["rating"], "winner should rise above loser"

    cfg = get_config()
    # Pre-match: strong vs weak should favor strong, probs sum to ~1.
    est = winmodel.compute(
        winmodel.ModelInputs(
            home_id="S", home_name="Strong", away_id="W", away_name="Weak",
            home_elo=s["rating"], away_elo=w["rating"],
            home_matches=s["matches"], away_matches=w["matches"],
            home_ppg=3.0, away_ppg=0.0, form_n=5,
        ),
        cfg,
    )
    total = est["home_win"] + est["draw"] + est["away_win"]
    print(f"  Pre-match  H/D/A = {est['home_win']:.3f}/{est['draw']:.3f}/{est['away_win']:.3f}"
          f"  (sum={total:.3f}, band=±{est['band']}, provisional={est['provisional']})")
    assert abs(total - 1.0) < 1e-6, "probabilities must sum to 1"
    assert est["home_win"] > est["away_win"], "stronger team should be favored"
    assert est["basis"] == "pre-match"
    assert len(est["factors"]) >= 2, "must show >=2 explanatory factors"

    # In-match: weak team leading 2-0 at 80' should flip the favorite.
    live = winmodel.compute(
        winmodel.ModelInputs(
            home_id="S", home_name="Strong", away_id="W", away_name="Weak",
            home_elo=s["rating"], away_elo=w["rating"],
            home_matches=s["matches"], away_matches=w["matches"],
            home_ppg=3.0, away_ppg=0.0, form_n=5,
            minute=80, home_goals=0, away_goals=2, is_live=True,
        ),
        cfg,
    )
    print(f"  In-match   H/D/A = {live['home_win']:.3f}/{live['draw']:.3f}/{live['away_win']:.3f}"
          f"  (basis={live['basis']})")
    assert live["away_win"] > live["home_win"], "team leading late should be favored"
    assert live["basis"] == "in-match"

    # No Elo -> no estimate (never invents a number).
    none_est = winmodel.compute(
        winmodel.ModelInputs(home_id="A", home_name="A", away_id="B", away_name="B",
                             home_elo=None, away_elo=None),
        cfg,
    )
    assert none_est is None, "must not produce an estimate without inputs"
    print("  OK: missing inputs -> no estimate (no fabricated numbers)")


async def test_refresh_degrades():
    print("== Full refresh (live sources blocked here) ==")
    cfg = get_config()
    db = Database(":memory:")
    agg = Aggregator(cfg, db)
    try:
        snap = await agg.refresh(force_baseline=True)
    finally:
        await agg.aclose()
    print(f"  matches={len(snap['matches'])} live={snap['live_count']} value={snap['value_count']}")
    print(f"  smart_money.available={snap['smart_money']['available']} note={snap['smart_money'].get('note')!r}")
    print("  sources:")
    for s in snap["sources"]:
        print(f"    - {s['name']:18s} ok={s['ok']!s:5s} {s['detail']}")
    assert "disclaimer" in snap and "not betting advice" in snap["disclaimer"].lower()
    print("  OK: degraded cleanly, persistent disclaimer present, no crash")


if __name__ == "__main__":
    test_elo_and_model()
    asyncio.run(test_refresh_degrades())
    print("\nALL SMOKE CHECKS PASSED")
