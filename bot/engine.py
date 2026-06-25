"""Paper-trading copy engine.

PAPER ONLY. No orders are ever sent anywhere. A "fill" is a row in SQLite priced
off the live best bid/ask plus configured slippage. Bankroll is virtual.

Accounting model (realized-PnL equity curve):
  * cash starts at ``engine.starting_bankroll``.
  * opening a position moves ``size_usd`` from cash into open exposure (cost basis).
  * at resolution a winning outcome pays ``shares × $1``; a losing one pays $0.
  * realized_pnl += payout − size_usd; cash += payout.
  * equity = cash + open_exposure = starting_bankroll + realized_pnl.
"""
from __future__ import annotations

from typing import Optional

from .config import Config
from .db import Database, now
from .logging_setup import get_logger
from .models import UP, Market, ObservedTrade, Quote

log = get_logger("engine")

K_CASH = "cash"
K_REALIZED = "realized_pnl"
K_ENABLED = "enabled"


class PaperEngine:
    def __init__(self, db: Database, cfg: Config):
        self.db = db
        self.cfg = cfg
        if self.db.get_state(K_CASH) is None:
            self.db.set_state(K_CASH, cfg.engine.starting_bankroll)
            self.db.set_state(K_REALIZED, 0.0)
        if self.db.get_state(K_ENABLED) is None:
            self.db.set_state(K_ENABLED, True)

    # ------------------------------------------------------------------ #
    # bankroll helpers
    # ------------------------------------------------------------------ #
    @property
    def cash(self) -> float:
        return float(self.db.get_state(K_CASH, self.cfg.engine.starting_bankroll))

    @property
    def realized_pnl(self) -> float:
        return float(self.db.get_state(K_REALIZED, 0.0))

    @property
    def equity(self) -> float:
        return self.cfg.engine.starting_bankroll + self.realized_pnl

    @property
    def enabled(self) -> bool:
        return bool(self.db.get_state(K_ENABLED, True))

    def set_enabled(self, value: bool) -> None:
        self.db.set_state(K_ENABLED, bool(value))
        log.info("bot %s", "ENABLED" if value else "DISABLED")

    def open_exposure(self) -> float:
        return sum(p["size_usd"] for p in self.db.open_positions())

    # ------------------------------------------------------------------ #
    # fill simulation
    # ------------------------------------------------------------------ #
    def _entry_fill_price(self, quote: Quote) -> Optional[float]:
        """BUY fills at best ask + slippage; fall back to mid if ask missing."""
        ref = quote.best_ask if quote.best_ask is not None else quote.mid
        if ref is None:
            return None
        slip = self.cfg.engine.slippage_bps / 10_000.0
        return min(max(ref * (1.0 + slip), 0.001), 0.999)

    def _target_size_usd(self) -> float:
        size = self.equity * self.cfg.engine.bankroll_fraction
        return min(size, self.cfg.engine.max_position_usd)

    def mirror(self, market: Market, trade: ObservedTrade, quote: Quote) -> Optional[int]:
        """Mirror a tracked wallet's entry as a paper position. Returns position id."""
        if not self.enabled:
            return None
        if trade.side == "SELL" and not self.cfg.engine.mirror_sells:
            return None
        if self.db.position_exists(market.condition_id, trade.wallet, trade.outcome):
            return None
        if len(self.db.open_positions()) >= self.cfg.engine.max_open_positions:
            log.warning("max_open_positions reached; skipping mirror")
            return None

        fill_price = self._entry_fill_price(quote)
        if fill_price is None:
            log.warning("no quote for %s; cannot mirror", trade.outcome)
            return None

        size_usd = self._target_size_usd()
        if size_usd < self.cfg.engine.min_position_usd:
            return None
        if size_usd > self.cash:
            log.warning("insufficient paper cash (%.2f) for size %.2f", self.cash, size_usd)
            return None

        shares = size_usd / fill_price
        pid = self.db.open_position({
            "condition_id": market.condition_id,
            "market_question": market.question,
            "source_wallet": trade.wallet,
            "outcome": trade.outcome,
            "token_id": market.token_for(trade.outcome),
            "entry_price": fill_price,
            "shares": shares,
            "size_usd": size_usd,
            "opened_at": now(),
            "market_end_time": market.end_time,
        })
        self.db.add_fill({
            "position_id": pid, "kind": "ENTRY", "side": "BUY", "price": fill_price,
            "shares": shares, "size_usd": size_usd,
            "slippage_bps": self.cfg.engine.slippage_bps,
            "note": f"copy {trade.wallet[:10]} @ ref {quote.best_ask}",
        })
        self.db.set_state(K_CASH, self.cash - size_usd)
        log.info(
            "PAPER ENTRY  %s %s  %.2f shares @ %.3f  ($%.2f)  copy=%s",
            market.condition_id, trade.outcome, shares, fill_price, size_usd,
            trade.wallet[:10],
        )
        return pid

    def settle_position(self, position: dict, resolved_outcome: str) -> float:
        """Settle one open position at resolution; returns realized pnl."""
        won = position["outcome"] == resolved_outcome
        payout = position["shares"] * (1.0 if won else 0.0)
        pnl = payout - position["size_usd"]
        exit_price = 1.0 if won else 0.0
        self.db.close_position(position["id"], resolved_outcome, exit_price, pnl)
        self.db.add_fill({
            "position_id": position["id"], "kind": "RESOLUTION",
            "side": "SETTLE", "price": exit_price, "shares": position["shares"],
            "size_usd": payout, "slippage_bps": 0.0,
            "note": f"resolved {resolved_outcome} ({'WIN' if won else 'LOSS'})",
        })
        self.db.set_state(K_CASH, self.cash + payout)
        self.db.set_state(K_REALIZED, self.realized_pnl + pnl)
        log.info(
            "PAPER SETTLE %s %s  %s  pnl=%+.2f  (payout $%.2f)",
            position["condition_id"], position["outcome"],
            "WIN " if won else "LOSS", pnl, payout,
        )
        return pnl

    def settle_market(self, market: Market, resolved_outcome: str) -> int:
        """Settle all open positions on a resolved market. Returns count settled."""
        count = 0
        for p in self.db.open_positions_for(market.condition_id):
            self.settle_position(dict(p), resolved_outcome)
            count += 1
        return count

    def snapshot_equity(self) -> None:
        self.db.record_equity(
            bankroll=self.cash,
            open_exposure=self.open_exposure(),
            realized_pnl=self.realized_pnl,
            open_positions=len(self.db.open_positions()),
        )
