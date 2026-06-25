"""LiveProvider — composes Gamma + CLOB + Data API + on-chain into one provider.

This is what runs against the real Polymarket/Polygon APIs. Every probe records
into ``source_health`` so the Step-1 review (and the dashboard) can show exactly
which sources returned data vs failed.
"""
from __future__ import annotations

from typing import Optional

from ..config import Config
from ..db import Database
from ..logging_setup import get_logger
from ..models import Market, ObservedTrade, Quote, SourceStatus
from .base import HttpClient, Provider
from .clob import ClobClient
from .data_api import DataApiClient
from .gamma import GammaClient
from .onchain import OnchainClient

log = get_logger("sources.live")


class LiveProvider(Provider):
    name = "live"

    def __init__(self, cfg: Config, db: Database):
        self.cfg = cfg
        self.db = db
        self.http = HttpClient(
            timeout=cfg.data.http_timeout_seconds,
            max_retries=cfg.data.max_retries,
            backoff=cfg.data.retry_backoff_seconds,
        )
        self.gamma = GammaClient(cfg, self.http)
        self.clob = ClobClient(cfg, self.http)
        self.data_api = DataApiClient(cfg, self.http)
        self.onchain = OnchainClient(cfg, self.http)

    # ------------------------------------------------------------------ #
    async def discover_market(self) -> Optional[Market]:
        try:
            m = await self.gamma.discover_btc_5m_market()
            if m:
                self.db.record_source(
                    "gamma", ok=True, detail=f"{m.slug} ({m.condition_id[:10]}…)")
                return m
            # None could mean reachable-but-empty OR blocked — disambiguate.
            await self.gamma.ping()  # raises if actually unreachable
            self.db.record_source(
                "gamma", ok=False, error="reachable, no active BTC 5-min market")
            return None
        except Exception as exc:  # noqa: BLE001
            self.db.record_source("gamma", ok=False, error=str(exc)[:200])
            return None

    async def get_quote(self, token_id: str) -> Optional[Quote]:
        try:
            q = await self.clob.get_quote(token_id)
            self.db.record_source(
                "clob", ok=q is not None and (q.best_bid is not None or q.best_ask is not None),
                error=None if q else "no quote",
                detail=(f"{token_id[:8]}… bid={q.best_bid} ask={q.best_ask}" if q else None),
            )
            return q
        except Exception as exc:  # noqa: BLE001
            self.db.record_source("clob", ok=False, error=str(exc)[:200])
            return None

    async def fetch_trades(
        self, condition_ids: list[str] | None, since_ts: int
    ) -> list[ObservedTrade]:
        out: list[ObservedTrade] = []
        cids = condition_ids or []

        # Primary: Data API tape per market.
        try:
            got_any = False
            for cid in cids:
                trades = await self.data_api.get_trades(condition_id=cid, taker_only=False)
                out.extend(t for t in trades if t.timestamp >= since_ts)
                got_any = True
            self.db.record_source(
                "data_api", ok=got_any, detail=f"{len(out)} trades since cutoff" if got_any else None,
                error=None if got_any else "no condition ids to query",
            )
        except Exception as exc:  # noqa: BLE001
            self.db.record_source("data_api", ok=False, error=str(exc)[:200])

        # Secondary: on-chain CTF Exchange fills (optional).
        if getattr(self.cfg.data, "enable_onchain", False) and self.onchain.configured:
            try:
                token_map: dict[str, tuple[str, str]] = {}  # token_id -> (condition_id, outcome)
                for cid in cids:
                    row = self.db.get_market(cid)
                    if row:
                        if row["up_token_id"]:
                            token_map[str(row["up_token_id"])] = (cid, "UP")
                        if row["down_token_id"]:
                            token_map[str(row["down_token_id"])] = (cid, "DOWN")
                fills = await self.onchain.fetch_fills(list(token_map.keys()) or None)
                for f in fills:
                    if f.token_id in token_map:
                        f.condition_id, f.outcome = token_map[f.token_id]
                    out.append(f)
                self.db.record_source("onchain", ok=True, detail=f"{len(fills)} fills")
            except Exception as exc:  # noqa: BLE001
                self.db.record_source("onchain", ok=False, error=str(exc)[:200])
        return out

    async def fetch_resolution(self, market: Market) -> Optional[str]:
        # Authoritative: CLOB tokens[].winner; fallback: Gamma outcomePrices.
        try:
            r = await self.clob.resolution_for(market.condition_id, market.up_token_id)
            if r:
                self.db.record_source("clob", ok=True, detail=f"resolved {market.condition_id[:10]} → {r}")
                return r
        except Exception as exc:  # noqa: BLE001
            self.db.record_source("clob", ok=False, error=str(exc)[:200])
        try:
            r = await self.gamma.resolution_for(market.condition_id)
            if r:
                self.db.record_source("gamma", ok=True, detail=f"resolved {market.condition_id[:10]} → {r}")
            return r
        except Exception as exc:  # noqa: BLE001
            self.db.record_source("gamma", ok=False, error=str(exc)[:200])
            return None

    # ------------------------------------------------------------------ #
    async def health_check(self) -> list[SourceStatus]:
        self.http.force_single = True
        try:
            return await self._health_check()
        finally:
            self.http.force_single = False

    async def _health_check(self) -> list[SourceStatus]:
        statuses: list[SourceStatus] = []

        # Gamma — ping first for honest reachability, then try discovery.
        m = None
        try:
            await self.gamma.ping()  # raises on 403/connect failure
            m = await self.gamma.discover_btc_5m_market()
            detail = m.slug if m else "reachable, no active BTC 5-min market right now"
            st = SourceStatus("gamma", True, detail=detail,
                              sample={"condition_id": m.condition_id, "question": m.question,
                                      "up_token": m.up_token_id, "down_token": m.down_token_id,
                                      "end_time": m.end_time} if m else None)
            self.db.record_source("gamma", ok=True, detail=detail)
        except Exception as exc:  # noqa: BLE001
            st = SourceStatus("gamma", False, error=str(exc)[:200])
            self.db.record_source("gamma", ok=False, error=str(exc)[:200])
        statuses.append(st)

        # CLOB
        try:
            alive = await self.clob.ok()
            sample = None
            if alive and m:
                q = await self.clob.get_quote(m.up_token_id)
                sample = {"up_bid": q.best_bid, "up_ask": q.best_ask} if q else None
            st = SourceStatus("clob", alive, detail="/ok reachable" if alive else "", sample=sample)
            self.db.record_source("clob", ok=alive, error=None if alive else "unreachable",
                                  detail=st.detail)
        except Exception as exc:  # noqa: BLE001
            st = SourceStatus("clob", False, error=str(exc)[:200])
            self.db.record_source("clob", ok=False, error=str(exc)[:200])
        statuses.append(st)

        # Data API — ping (raw, raises on failure) before the swallowing helpers.
        try:
            await self.data_api.ping()
            cid = m.condition_id if m else None
            trades = await self.data_api.get_trades(condition_id=cid, limit=5) if cid else []
            board = await self.data_api.get_leaderboard(limit=5)
            detail = f"{len(trades)} recent trades, {len(board)} leaderboard wallets"
            st = SourceStatus("data_api", True, detail=detail,
                              sample={"sample_trade_wallets": [t.wallet[:10] for t in trades[:3]],
                                      "leaderboard_top": board[:3]})
            self.db.record_source("data_api", ok=True, detail=detail)
        except Exception as exc:  # noqa: BLE001
            st = SourceStatus("data_api", False, error=str(exc)[:200])
            self.db.record_source("data_api", ok=False, error=str(exc)[:200])
        statuses.append(st)

        # On-chain (only if configured)
        if self.onchain.configured:
            ok, detail = await self.onchain.health()
            statuses.append(SourceStatus("onchain", ok, detail=detail if ok else "",
                                         error="" if ok else detail))
            self.db.record_source("onchain", ok=ok, error=None if ok else detail, detail=detail)
        else:
            statuses.append(SourceStatus("onchain", False,
                                         detail="disabled (no POLYGON_RPC_URL)",
                                         error="not configured"))

        return statuses

    async def aclose(self) -> None:
        await self.http.aclose()
