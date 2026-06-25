"""Main paper-trading loop orchestration.

Ties together the provider (live or sim), the wallet scorer, and the paper
engine. Handles the 5-minute market rollover and auto-resolution.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional

from .config import Config
from .db import Database, now
from .engine import PaperEngine
from .logging_setup import get_logger
from .models import Market
from .provider import build_provider
from .sources.base import Provider
from .wallets import rank_wallets, top_wallet_addresses

log = get_logger("loop")


@dataclass
class CycleReport:
    """Summary of one loop iteration (used by `python -m bot cycle`)."""
    market: Optional[Market] = None
    rolled_over: bool = False
    new_trades: int = 0
    mirrored: int = 0
    settled: int = 0
    settled_pnl: float = 0.0
    reranked: bool = False
    top_wallets: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class Bot:
    def __init__(self, cfg: Config, db: Database):
        self.cfg = cfg
        self.db = db
        self.engine = PaperEngine(db, cfg)
        self.provider: Optional[Provider] = None
        self._last_poll = now() - int(cfg.data.poll_interval_seconds) - 1
        self._last_rank = 0
        self._current_condition: Optional[str] = None
        self._stop = asyncio.Event()

    async def setup(self) -> None:
        self.provider = await build_provider(self.cfg, self.db)
        # Seed/backfill history so wallet ranking has data immediately:
        # sim seeds synthetically; live backfills recent resolved markets + trades.
        await self.provider.prepare_history(self.db, self.cfg)
        rank_wallets(self.db, self.cfg)
        self._last_rank = now()
        self.engine.snapshot_equity()

    async def teardown(self) -> None:
        if self.provider:
            await self.provider.aclose()

    # ------------------------------------------------------------------ #
    async def _resolve_closed_markets(self, report: CycleReport) -> None:
        """Auto-resolve any open positions whose market has closed."""
        assert self.provider is not None
        open_conditions = {p["condition_id"] for p in self.db.open_positions()}
        for cid in open_conditions:
            row = self.db.get_market(cid)
            if not row:
                continue
            market = Market(
                condition_id=row["condition_id"], question=row["question"] or "",
                slug=row["slug"] or "", up_token_id=row["up_token_id"] or "",
                down_token_id=row["down_token_id"] or "",
                start_time=row["start_time"] or 0, end_time=row["end_time"] or 0,
                resolved_outcome=row["resolved_outcome"],
            )
            if self.provider.now() < (market.end_time or 0):
                continue  # window not closed yet (per provider clock)
            outcome = market.resolved_outcome or await self.provider.fetch_resolution(market)
            if not outcome:
                report.notes.append(f"{cid} closed but resolution not yet available")
                continue
            db_market = market.as_db()
            db_market["resolved_outcome"] = outcome
            db_market["resolved_at"] = now()
            db_market["closed"] = 1
            db_market["active"] = 0
            self.db.upsert_market(db_market)
            n = self.engine.settle_market(market, outcome)
            if n:
                report.settled += n
                report.settled_pnl += sum(
                    p["pnl"] for p in self.db.closed_positions(limit=n)
                )

    async def _maybe_rerank(self, report: CycleReport) -> None:
        assert self.provider is not None
        if self.provider.now() - self._last_rank >= self.cfg.wallets.refresh_interval_seconds:
            rank_wallets(self.db, self.cfg)
            self._last_rank = self.provider.now()
            report.reranked = True

    async def run_once(self) -> CycleReport:
        assert self.provider is not None
        report = CycleReport()

        # 1) discover current market + handle rollover
        market = await self.provider.discover_market()
        if market is None:
            report.notes.append("no active BTC 5-min market found")
            self.engine.snapshot_equity()
            return report
        report.market = market
        self.db.upsert_market(market.as_db())
        if self._current_condition and self._current_condition != market.condition_id:
            report.rolled_over = True
            log.info("market rollover: %s → %s", self._current_condition, market.condition_id)
        self._current_condition = market.condition_id

        # 2) settle anything that has resolved
        await self._resolve_closed_markets(report)

        # 3) refresh wallet rankings periodically
        await self._maybe_rerank(report)
        top = top_wallet_addresses(self.db, self.cfg)
        report.top_wallets = sorted(top)

        # 4) ingest recent tracked-wallet trades; mirror top-N entries
        since = self._last_poll
        trades = await self.provider.fetch_trades([market.condition_id], since)
        for t in trades:
            self.db.insert_trade(t.as_db())
            report.new_trades += 1
        if self.engine.enabled:
            for t in trades:
                if t.wallet not in top:
                    continue
                if t.side != "BUY":
                    continue
                if t.condition_id != market.condition_id:
                    continue
                token = market.token_for(t.outcome)
                quote = await self.provider.get_quote(token)
                if quote is None:
                    continue
                pid = self.engine.mirror(market, t, quote)
                if pid:
                    report.mirrored += 1
        self._last_poll = self.provider.now()

        # 5) record equity point
        self.engine.snapshot_equity()
        return report

    async def run_forever(self) -> None:
        await self.setup()
        log.info(
            "paper loop started | mode=%s | poll=%.0fs | bankroll=$%.2f | enabled=%s",
            self.cfg.data.mode, self.cfg.data.poll_interval_seconds,
            self.engine.equity, self.engine.enabled,
        )
        try:
            while not self._stop.is_set():
                try:
                    rep = await self.run_once()
                    if rep.market:
                        log.info(
                            "tick | %s | new_trades=%d mirrored=%d settled=%d | "
                            "equity=$%.2f cash=$%.2f open=%d",
                            rep.market.condition_id, rep.new_trades, rep.mirrored,
                            rep.settled, self.engine.equity, self.engine.cash,
                            len(self.db.open_positions()),
                        )
                except Exception:  # noqa: BLE001 - keep the loop alive
                    log.exception("error in loop iteration")
                try:
                    await asyncio.wait_for(
                        self._stop.wait(), timeout=self.cfg.data.poll_interval_seconds
                    )
                except asyncio.TimeoutError:
                    pass
        finally:
            await self.teardown()

    def stop(self) -> None:
        self._stop.set()
