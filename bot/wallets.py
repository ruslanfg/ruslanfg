"""Tracked-wallet discovery, grading and ranking.

Works identically for live and simulated data: it reads observed ``trades`` and
the ``markets`` they were placed on (with resolved outcomes) from the DB, grades
each trade's realized PnL, then ranks wallets with a configurable scoring
function.

Scoring (weights from config.yaml ``wallets.scoring``, normalized internally):

    score = wr_w · win_rate^wr_exp  +  pnl_w · norm(volume-weighted PnL)
                                     +  vol_w · norm(volume)

This blends *win rate* with *volume-weighted realized PnL* (and a small activity
bonus), matching the spec's "win rate × volume-weighted PnL, configurable
weights".
"""
from __future__ import annotations

from typing import Iterable

from .config import Config
from .db import Database, now
from .logging_setup import get_logger
from .models import DOWN, UP, WalletScore

log = get_logger("wallets")


def _trade_pnl(side: str, outcome: str, price: float, size: float, resolved: str) -> float:
    """Realized PnL of one graded trade (binary outcome pays 1 or 0 per share)."""
    won = outcome == resolved
    if side == "BUY":
        return size * ((1.0 - price) if won else (-price))
    # SELL = short the outcome token
    return size * ((price - 1.0) if won else price)


def _normalize(values: list[float]) -> list[float]:
    """Min-max normalize to [0,1]; handles all-equal and negative ranges."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return [0.5 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def compute_wallet_stats(db: Database, wallet: str, since: int, lookback_days: int) -> WalletScore:
    rows = db.wallet_trades(wallet, since)
    wins = losses = graded = 0
    realized = 0.0
    volume = 0.0
    first_seen = last_seen = None
    for r in rows:
        ts = r["timestamp"]
        first_seen = ts if first_seen is None else min(first_seen, ts)
        last_seen = ts if last_seen is None else max(last_seen, ts)
        mkt = db.get_market(r["condition_id"]) if r["condition_id"] else None
        if not mkt or not mkt["resolved_outcome"]:
            continue  # only grade trades on resolved markets
        pnl = _trade_pnl(r["side"], r["outcome"], r["price"], r["size"], mkt["resolved_outcome"])
        graded += 1
        realized += pnl
        volume += (r["usd"] or (r["price"] * r["size"]))
        if pnl > 0:
            wins += 1
        else:
            losses += 1
    win_rate = (wins / graded) if graded else 0.0
    return WalletScore(
        wallet=wallet,
        trades_count=graded,
        wins=wins,
        losses=losses,
        win_rate=win_rate,
        realized_pnl=realized,
        volume=volume,
        vw_pnl=realized,           # realized PnL already scales with size (volume)
        lookback_days=lookback_days,
        first_seen=first_seen,
        last_seen=last_seen,
    )


def rank_wallets(db: Database, cfg: Config) -> list[WalletScore]:
    """Recompute stats & scores for every wallet seen in the lookback; persist."""
    sc = cfg.wallets.scoring
    lookback = cfg.wallets.lookback_days
    since = now() - lookback * 86400

    candidates: set[str] = set(db.distinct_wallets(since))
    candidates.update(w["wallet"] for w in db.all_wallets())

    stats = [compute_wallet_stats(db, w, since, lookback) for w in candidates]
    if not stats:
        return []

    # Normalize PnL & volume across the cohort for the additive score.
    norm_pnl = _normalize([s.vw_pnl for s in stats])
    norm_vol = _normalize([s.volume for s in stats])
    w_sum = max(sc.win_rate_weight + sc.pnl_weight + sc.volume_weight, 1e-9)
    for s, npnl, nvol in zip(stats, norm_pnl, norm_vol):
        wr_comp = s.win_rate ** sc.win_rate_exponent
        s.score = (
            sc.win_rate_weight * wr_comp
            + sc.pnl_weight * npnl
            + sc.volume_weight * nvol
        ) / w_sum

    # Rank only wallets meeting the minimum-trades bar; others get rank=None.
    qualifying = [s for s in stats if s.trades_count >= cfg.wallets.min_trades]
    qualifying.sort(key=lambda s: (s.score, s.realized_pnl), reverse=True)
    for i, s in enumerate(qualifying, start=1):
        s.rank = i

    for s in stats:
        db.upsert_wallet({
            "wallet": s.wallet, "first_seen": s.first_seen or now(),
            "last_seen": s.last_seen or now(), "trades_count": s.trades_count,
            "wins": s.wins, "losses": s.losses, "win_rate": s.win_rate,
            "realized_pnl": s.realized_pnl, "volume": s.volume, "vw_pnl": s.vw_pnl,
            "score": s.score, "rank": s.rank, "lookback_days": lookback,
        })

    # Trim universe to max_wallets_tracked (keep best-scoring).
    all_sorted = sorted(stats, key=lambda s: s.score, reverse=True)
    keep = {s.wallet for s in all_sorted[: cfg.wallets.max_wallets_tracked]}
    for s in all_sorted[cfg.wallets.max_wallets_tracked:]:
        db.execute("DELETE FROM tracked_wallets WHERE wallet=?", (s.wallet,))
    _ = keep

    log.info(
        "ranked %d wallets (%d qualify, min_trades=%d, lookback=%dd)",
        len(stats), len(qualifying), cfg.wallets.min_trades, lookback,
    )
    return qualifying


def top_wallet_addresses(db: Database, cfg: Config) -> set[str]:
    return {w["wallet"] for w in db.top_wallets(cfg.wallets.top_n, cfg.wallets.min_trades)}
