"""Data API client — trade tape & (PnL/VOL) leaderboard for wallet discovery.

Base: https://data-api.polymarket.com (public, no auth, camelCase fields).

Used for trader tracking: pull the /trades tape for the BTC 5-min market(s) to
discover and grade wallets. There IS an official /v1/leaderboard (PnL or VOL,
DAY/WEEK/MONTH/ALL) but it does NOT expose WIN-RATE — per the spec we compute
win rate & realized PnL ourselves from /trades + resolved outcomes. The
leaderboard is used only to seed the candidate-wallet universe.
"""
from __future__ import annotations

from typing import Optional

from ..config import Config
from ..logging_setup import get_logger
from ..models import DOWN, UP, ObservedTrade
from .base import HttpClient

log = get_logger("sources.data_api")


class DataApiClient:
    def __init__(self, cfg: Config, http: HttpClient):
        self.cfg = cfg
        self.http = http
        self.base = cfg.data.data_api_base_url.rstrip("/")

    async def ping(self) -> bool:
        """Raw reachability probe — raises on network/HTTP failure (e.g. 403)."""
        await self.http.get_json(f"{self.base}/trades", {"limit": 1})
        return True

    async def get_trades(
        self,
        condition_id: str | None = None,
        user: str | None = None,
        limit: int = 500,
        offset: int = 0,
        taker_only: bool = False,
    ) -> list[ObservedTrade]:
        params: dict[str, object] = {"limit": min(limit, 500), "offset": offset,
                                     "takerOnly": str(taker_only).lower()}
        if condition_id:
            params["market"] = condition_id
        if user:
            params["user"] = user
        try:
            data = await self.http.get_json(f"{self.base}/trades", params)
        except Exception as exc:  # noqa: BLE001
            log.debug("data_api get_trades failed: %s", exc)
            return []
        out: list[ObservedTrade] = []
        for t in data if isinstance(data, list) else []:
            wallet = t.get("proxyWallet")
            if not wallet:
                continue
            idx = t.get("outcomeIndex")
            outcome = UP if idx in (0, "0") else DOWN if idx in (1, "1") else None
            if outcome is None and t.get("outcome"):
                label = str(t["outcome"]).lower()
                outcome = UP if label in ("up", "yes") else DOWN
            try:
                price = float(t.get("price"))
                size = float(t.get("size"))
            except (TypeError, ValueError):
                continue
            out.append(ObservedTrade(
                wallet=wallet,
                condition_id=t.get("conditionId"),
                token_id=str(t.get("asset")) if t.get("asset") is not None else None,
                outcome=outcome,
                side=(t.get("side") or "BUY").upper(),
                price=price,
                size=size,
                timestamp=int(t.get("timestamp", 0)),
                tx_hash=t.get("transactionHash"),
                source="data_api",
            ))
        return out

    async def get_leaderboard(
        self, order_by: str = "PNL", time_period: str = "WEEK",
        category: str = "CRYPTO", limit: int = 50,
    ) -> list[str]:
        """Seed candidate wallets from the official PnL/VOL leaderboard."""
        try:
            data = await self.http.get_json(
                f"{self.base}/v1/leaderboard",
                {"orderBy": order_by, "timePeriod": time_period,
                 "category": category, "limit": min(limit, 50)},
            )
        except Exception as exc:  # noqa: BLE001
            log.debug("data_api leaderboard failed: %s", exc)
            return []
        return [row["proxyWallet"] for row in (data if isinstance(data, list) else [])
                if row.get("proxyWallet")]
