"""Gamma API client — market discovery & resolution.

Base: https://gamma-api.polymarket.com (public, no auth).

The BTC 5-minute market has a DETERMINISTIC slug: ``btc-updown-5m-{window_ts}``
where ``window_ts = now - (now % 300)`` (start of the current 5-min window). We
resolve it by slug (robust, no indexing latency), with a tag/active-list fallback.

GOTCHAS handled here (from the verified API research):
  * Gamma is camelCase (conditionId, clobTokenIds, endDate, outcomePrices).
  * clobTokenIds / outcomes / outcomePrices are JSON-ENCODED STRINGS — json.loads
    them before indexing.
  * Index 0 == the "Up"/first outcome token; the literal label may be 'Up' or
    'Yes', so we key off index, not the string.
  * 5-min markets resolve via Chainlink (Up if close >= open) — NOT UMA; do not
    gate on umaResolutionStatuses.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Optional

from ..config import Config
from ..logging_setup import get_logger
from ..models import DOWN, UP, Market
from .base import HttpClient

log = get_logger("sources.gamma")

WINDOW_SECONDS = 300


def _iso_to_epoch(s: str | None) -> int:
    if not s:
        return 0
    try:
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
    except (ValueError, AttributeError):
        return 0


def _maybe_json_list(value: Any) -> list:
    """Gamma returns clobTokenIds/outcomes/outcomePrices as JSON strings."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def current_window_ts(now: int | None = None) -> int:
    now = now if now is not None else int(time.time())
    return now - (now % WINDOW_SECONDS)


def btc_slug(window_ts: int) -> str:
    return f"btc-updown-5m-{window_ts}"


class GammaClient:
    def __init__(self, cfg: Config, http: HttpClient):
        self.cfg = cfg
        self.http = http
        self.base = cfg.data.gamma_base_url.rstrip("/")

    # ------------------------------------------------------------------ #
    def _market_from_obj(self, m: dict[str, Any]) -> Optional[Market]:
        token_ids = _maybe_json_list(m.get("clobTokenIds"))
        if len(token_ids) < 2:
            return None
        cid = m.get("conditionId") or m.get("condition_id")
        if not cid:
            return None
        outcomes = _maybe_json_list(m.get("outcomes")) or ["Up", "Down"]
        resolved = None
        if m.get("closed"):
            prices = [float(p) for p in _maybe_json_list(m.get("outcomePrices")) if p != ""]
            if prices:
                resolved = UP if prices[0] >= 0.5 else DOWN
        return Market(
            condition_id=cid,
            question=m.get("question") or m.get("title") or "Bitcoin Up or Down — 5 Minute",
            slug=m.get("slug") or "",
            up_token_id=str(token_ids[0]),
            down_token_id=str(token_ids[1]),
            start_time=_iso_to_epoch(m.get("startDate")),
            end_time=_iso_to_epoch(m.get("endDate") or m.get("endDateIso")),
            neg_risk=bool(m.get("negRisk", False)),
            active=bool(m.get("active", True)),
            closed=bool(m.get("closed", False)),
            resolved_outcome=resolved,
            source="live",
            raw={"outcomes": outcomes, "acceptingOrders": m.get("acceptingOrders")},
        )

    async def _markets_from_response(self, data: Any) -> list[Market]:
        markets: list[Market] = []
        items = data if isinstance(data, list) else data.get("data", []) if isinstance(data, dict) else []
        for obj in items:
            # /events returns events with nested markets[]; /markets returns markets directly.
            if isinstance(obj, dict) and "markets" in obj and isinstance(obj["markets"], list):
                for sub in obj["markets"]:
                    mk = self._market_from_obj(sub)
                    if mk:
                        markets.append(mk)
            elif isinstance(obj, dict):
                mk = self._market_from_obj(obj)
                if mk:
                    markets.append(mk)
        return markets

    async def discover_btc_5m_market(self) -> Optional[Market]:
        """Find the currently-active BTC 5-min market (deterministic slug first)."""
        wts = current_window_ts()
        slug = btc_slug(wts)

        # 1) Deterministic slug via /events (event wraps the Up/Down market).
        for url, params in (
            (f"{self.base}/events", {"slug": slug}),
            (f"{self.base}/markets", {"slug": slug}),
        ):
            try:
                data = await self.http.get_json(url, params)
                markets = await self._markets_from_response(data)
                if markets:
                    return markets[0]
            except Exception as exc:  # noqa: BLE001
                log.debug("gamma discover via %s failed: %s", url, exc)

        # 2) Fallback: list active markets, match by slug prefix / question text.
        try:
            data = await self.http.get_json(
                f"{self.base}/markets",
                {"active": "true", "closed": "false", "order": "endDate",
                 "ascending": "true", "limit": 200},
            )
            markets = await self._markets_from_response(data)
            now = int(time.time())
            cands = [
                m for m in markets
                if (m.slug.startswith("btc-updown-5m")
                    or any(q in (m.question or "").lower() for q in self.cfg.market.question_contains))
                and m.end_time > now
            ]
            cands.sort(key=lambda m: m.end_time)
            if cands:
                return cands[0]
        except Exception as exc:  # noqa: BLE001
            log.warning("gamma fallback discovery failed: %s", exc)
        return None

    async def ping(self) -> bool:
        """Raw reachability probe — raises on network/HTTP failure (e.g. 403)."""
        await self.http.get_json(f"{self.base}/markets", {"limit": 1})
        return True

    async def get_market_by_condition(self, condition_id: str) -> Optional[Market]:
        try:
            data = await self.http.get_json(
                f"{self.base}/markets", {"condition_ids": condition_id}
            )
            markets = await self._markets_from_response(data)
            return markets[0] if markets else None
        except Exception as exc:  # noqa: BLE001
            log.debug("gamma get_market_by_condition failed: %s", exc)
            return None

    async def resolution_for(self, condition_id: str) -> Optional[str]:
        m = await self.get_market_by_condition(condition_id)
        return m.resolved_outcome if m else None
