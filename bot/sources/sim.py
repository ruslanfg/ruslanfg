"""Deterministic offline simulator.

Implements the full :class:`Provider` interface with NO network access, so the
loop, engine, API and dashboard can be exercised end-to-end anywhere (e.g. a
sandbox where Polymarket egress is blocked). Everything is seeded, so a given
config reproduces the exact same markets, prices, resolutions and wallet
behaviour across processes (loop + API) and across runs.

Model: BTC follows a driftless geometric Brownian motion. Each 5-minute window
``w`` has S sub-steps; the window's log-returns are seeded by ``(seed, w)``. A
market resolves UP iff the close price exceeds the open. The fair price of the
UP token at fraction ``f`` of the window is P(final return > 0 | current
return), i.e. a clean Brownian-bridge style probability that drifts toward 0/1
as the window closes.
"""
from __future__ import annotations

import math
import random
import zlib
from datetime import datetime, timezone
from typing import Optional

from ..config import Config
from ..db import Database
from ..logging_setup import get_logger
from ..models import DOWN, UP, Market, ObservedTrade, Quote, SourceStatus

log = get_logger("sources.sim")

# Fixed anchor so window indices & prices are identical across processes/runs.
REFERENCE_EPOCH = int(datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp())
SUB_STEPS = 30          # intra-window granularity
HALF_SPREAD = 0.01      # simulated bid/ask half-spread (price units)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _seed(*parts) -> int:
    """Fast, process-independent deterministic seed (crc32 of the joined parts)."""
    return zlib.crc32("|".join(str(p) for p in parts).encode())


class SimProvider:
    name = "sim"

    def __init__(self, cfg: Config, clock=None):
        self.cfg = cfg
        self._clock = clock  # injectable for tests; defaults to time.time
        self.tick = (
            cfg.sim.accelerated_window_seconds
            if cfg.sim.accelerate
            else cfg.market.duration_minutes * 60
        )
        self.base = cfg.sim.btc_start_price
        self.window_sigma = cfg.sim.btc_volatility_bps / 10_000.0  # per-window stdev (log)
        self.sub_sigma = self.window_sigma / math.sqrt(SUB_STEPS)
        self._open_cache: dict[int, float] = {0: self.base}
        self._bridge_cache: dict[int, list[float]] = {}
        self._wallets = self._make_wallets()

    # ------------------------------------------------------------------ #
    # time / windows
    # ------------------------------------------------------------------ #
    def _now(self) -> float:
        if self._clock is not None:
            return self._clock()
        import time
        return time.time()

    def now(self) -> int:
        return int(self._now())

    def window_index(self, t: float) -> int:
        return int(math.floor((t - REFERENCE_EPOCH) / self.tick))

    def window_start(self, w: int) -> int:
        return REFERENCE_EPOCH + w * self.tick

    # ------------------------------------------------------------------ #
    # price path (deterministic)
    # ------------------------------------------------------------------ #
    def _total_return(self, w: int) -> float:
        """Window log-return (single draw → cheap chaining)."""
        return random.Random(_seed(self.cfg.sim.seed,"R",w)).gauss(0.0, self.window_sigma)

    def _open_price(self, w: int) -> float:
        """open(w), chained from the fixed reference window (memoized)."""
        if w in self._open_cache:
            return self._open_cache[w]
        if w > 0:
            start = max(k for k in self._open_cache if k <= w)
            price = self._open_cache[start]
            for i in range(start, w):
                price *= math.exp(self._total_return(i))
                self._open_cache[i + 1] = price
            return self._open_cache[w]
        start = min(k for k in self._open_cache if k >= w)
        price = self._open_cache[start]
        for i in range(start, w, -1):
            price /= math.exp(self._total_return(i - 1))
            self._open_cache[i - 1] = price
        return self._open_cache[w]

    def _bridge(self, w: int) -> list[float]:
        """Cumulative intra-window log-returns (Brownian bridge) hitting the
        window's total return at f=1, so close(w) is consistent with open(w+1).
        Returns S+1 values: index 0 == 0, index S == total_return(w)."""
        if w in self._bridge_cache:
            return self._bridge_cache[w]
        rng = random.Random(_seed(self.cfg.sim.seed,"B",w))
        incs = [rng.gauss(0.0, self.sub_sigma) for _ in range(SUB_STEPS)]
        cum, s = [0.0], 0.0
        for x in incs:
            s += x
            cum.append(s)
        total_noise = cum[-1]
        total = self._total_return(w)
        path = [cum[k] - (k / SUB_STEPS) * total_noise + (k / SUB_STEPS) * total
                for k in range(SUB_STEPS + 1)]
        self._bridge_cache[w] = path
        return path

    def _price_at(self, w: int, f: float) -> float:
        """Spot price at fraction f in [0,1] of window w."""
        f = min(max(f, 0.0), 1.0)
        path = self._bridge(w)
        x = f * SUB_STEPS
        k = min(int(x), SUB_STEPS - 1)
        val = path[k] + (x - k) * (path[k + 1] - path[k])
        return self._open_price(w) * math.exp(val)

    def _close_price(self, w: int) -> float:
        return self._open_price(w + 1)

    def _fair_up(self, w: int, f: float) -> float:
        """P(close > open | current spot) — the fair price of the UP token."""
        open_p = self._open_price(w)
        spot = self._price_at(w, f)
        x = math.log(spot / open_p)
        sigma_rem = self.window_sigma * math.sqrt(max(1.0 - f, 1e-6))
        p = _norm_cdf(x / sigma_rem) if sigma_rem > 1e-9 else (1.0 if x > 0 else 0.0)
        return min(max(p, 0.02), 0.98)

    def _outcome(self, w: int) -> str:
        return UP if self._close_price(w) > self._open_price(w) else DOWN

    # ------------------------------------------------------------------ #
    # synthetic wallets
    # ------------------------------------------------------------------ #
    def _make_wallets(self) -> list[dict]:
        rng = random.Random(_seed(self.cfg.sim.seed,"wallets"))
        wallets = []
        for i in range(self.cfg.sim.num_wallets):
            addr = "0x" + "".join(rng.choice("0123456789abcdef") for _ in range(40))
            wallets.append({
                "wallet": addr,
                "skill": rng.uniform(0.40, 0.78),     # P(picks the winning side)
                "rate": rng.uniform(0.15, 0.6),        # P(trades a given window)
                "size_mu": rng.uniform(20, 400),       # typical position size (shares)
            })
        return wallets

    def _wallet_trade_for_window(self, wal: dict, w: int) -> Optional[dict]:
        """Deterministic decision: does this wallet trade window w, and how?"""
        rng = random.Random(_seed(self.cfg.sim.seed,"trade",w,wal["wallet"]))
        if rng.random() > wal["rate"]:
            return None
        outcome = self._outcome(w)
        picked = outcome if rng.random() < wal["skill"] else (DOWN if outcome == UP else UP)
        f = rng.uniform(0.02, 0.7)                      # enters early/mid window
        price = self._fair_up(w, f) if picked == UP else 1.0 - self._fair_up(w, f)
        price = min(max(price, 0.02), 0.98)
        size = max(1.0, rng.gauss(wal["size_mu"], wal["size_mu"] * 0.3))
        ts = self.window_start(w) + int(f * self.tick)
        return {"outcome": picked, "side": "BUY", "price": round(price, 3),
                "size": round(size, 2), "timestamp": ts, "f": f}

    # ------------------------------------------------------------------ #
    # Provider interface
    # ------------------------------------------------------------------ #
    def _build_market(self, w: int) -> Market:
        start = self.window_start(w)
        end = start + self.tick
        now = self._now()
        closed = now >= end
        return Market(
            condition_id=f"sim-{w}",
            question=f"Bitcoin Up or Down — 5 Minute (sim window {w})",
            slug=f"bitcoin-up-or-down-sim-{w}",
            up_token_id=f"sim-{w}-UP",
            down_token_id=f"sim-{w}-DOWN",
            start_time=start,
            end_time=end,
            neg_risk=False,
            active=not closed,
            closed=closed,
            resolved_outcome=self._outcome(w) if closed else None,
            source="sim",
            raw={"window": w, "open": round(self._open_price(w), 2),
                 "close": round(self._close_price(w), 2)},
        )

    async def discover_market(self) -> Optional[Market]:
        return self._build_market(self.window_index(self._now()))

    def _parse_token(self, token_id: str) -> tuple[int, str]:
        # "sim-<w>-UP" / "sim-<w>-DOWN"
        _, w, side = token_id.rsplit("-", 2)
        return int(w), side

    async def get_quote(self, token_id: str) -> Optional[Quote]:
        try:
            w, side = self._parse_token(token_id)
        except ValueError:
            return None
        now = self._now()
        start = self.window_start(w)
        f = (now - start) / self.tick
        if f >= 1.0:  # window closed → price pinned to resolution
            up = 1.0 if self._outcome(w) == UP else 0.0
        else:
            up = self._fair_up(w, max(f, 0.0))
        fair = up if side == UP else 1.0 - up
        bid = round(min(max(fair - HALF_SPREAD, 0.01), 0.99), 3)
        ask = round(min(max(fair + HALF_SPREAD, 0.01), 0.99), 3)
        return Quote(token_id=token_id, best_bid=bid, best_ask=ask)

    async def fetch_trades(
        self, condition_ids: list[str] | None, since_ts: int
    ) -> list[ObservedTrade]:
        """Live entries on the current (and given) windows since `since_ts`."""
        now = self._now()
        windows: list[int] = []
        if condition_ids:
            for cid in condition_ids:
                try:
                    windows.append(int(cid.split("-")[1]))
                except (IndexError, ValueError):
                    continue
        else:
            windows.append(self.window_index(now))
        out: list[ObservedTrade] = []
        for w in windows:
            for wal in self._wallets:
                t = self._wallet_trade_for_window(wal, w)
                if not t:
                    continue
                if t["timestamp"] < since_ts or t["timestamp"] > now:
                    continue
                token = f"sim-{w}-{t['outcome']}"
                out.append(ObservedTrade(
                    wallet=wal["wallet"], condition_id=f"sim-{w}", token_id=token,
                    outcome=t["outcome"], side=t["side"], price=t["price"],
                    size=t["size"], timestamp=t["timestamp"],
                    tx_hash=f"0xsim{w}{wal['wallet'][2:10]}", source="sim",
                ))
        out.sort(key=lambda x: x.timestamp)
        return out

    async def fetch_resolution(self, market: Market) -> Optional[str]:
        try:
            w = int(market.condition_id.split("-")[1])
        except (IndexError, ValueError):
            return None
        if self._now() < self.window_start(w) + self.tick:
            return None
        return self._outcome(w)

    async def health_check(self) -> list[SourceStatus]:
        m = await self.discover_market()
        return [SourceStatus(
            name="simulator",
            ok=True,
            detail=f"window {self.window_index(self._now())} | BTC≈${self._price_at(self.window_index(self._now()), (self._now()-self.window_start(self.window_index(self._now())))/self.tick):,.0f}",
            sample={"condition_id": m.condition_id, "question": m.question} if m else None,
        )]

    # ------------------------------------------------------------------ #
    # history bootstrap (sim-only): seed resolved markets + wallet trades
    # ------------------------------------------------------------------ #
    def bootstrap_history(self, db: Database, lookback_days: int, max_windows: int = 300) -> int:
        now = self._now()
        w_now = self.window_index(now)
        n_windows = min(int(lookback_days * 86400 / self.tick), max_windows)
        markets: list[dict] = []
        trades: list[dict] = []
        for w in range(w_now - n_windows, w_now):
            markets.append(self._build_market(w).as_db())  # closed & resolved
            for wal in self._wallets:
                t = self._wallet_trade_for_window(wal, w)
                if not t:
                    continue
                token = f"sim-{w}-{t['outcome']}"
                trades.append(ObservedTrade(
                    wallet=wal["wallet"], condition_id=f"sim-{w}", token_id=token,
                    outcome=t["outcome"], side=t["side"], price=t["price"],
                    size=t["size"], timestamp=t["timestamp"],
                    tx_hash=f"0xsim{w}{wal['wallet'][2:10]}", source="sim",
                ).as_db())
        db.bulk_upsert_markets(markets)
        inserted = db.bulk_insert_trades(trades)
        log.info("sim bootstrap: seeded %d windows, %d trades", n_windows, inserted)
        return inserted

    async def aclose(self) -> None:
        pass
