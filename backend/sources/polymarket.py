"""Polymarket public APIs (no key required):

  * gamma-api  -> market prices (implied probabilities)
  * lb-api     -> public trader leaderboard (P&L / volume)
  * data-api   -> a trader's CURRENTLY OPEN positions

HARD CONSTRAINT honoured here: the positions endpoint returns only positions a
trader has ALREADY taken (public on-chain/API data). We never predict, infer, or
fabricate future bets. A trader with no open World Cup position yields an empty
list, surfaced as "no current position".

Endpoint shapes vary over time, so every parser is defensive and the caller
degrades to "data unavailable" on any error.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from ..http_client import HttpClient, SourceError
from .odds import normalize_team


def _maybe_json_list(value: Any) -> list:
    """gamma returns `outcomes`/`outcomePrices` as JSON-encoded strings."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (ValueError, TypeError):
            return []
    return []


def _first(d: dict, *keys, default=None):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def _to_float(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class PolymarketSource:
    name = "polymarket"
    label = "Polymarket (public prediction market)"

    def __init__(self, cfg, http: HttpClient):
        self.cfg = cfg.polymarket
        self.http = http

    # -- markets / odds -------------------------------------------------------
    async def fetch_markets(self, limit: int = 500) -> list[dict[str, Any]]:
        """Active markets, normalized. Caller filters to the World Cup by team
        names + WC query terms (handles per-match 3-way markets)."""
        url = f"{self.cfg.gamma_url}/markets"
        params = {
            "closed": "false",
            "active": "true",
            "limit": str(limit),
            "order": "volume24hr",
            "ascending": "false",
        }
        data = await self.http.get_json(url, params=params)
        rows = data if isinstance(data, list) else (data.get("data") if isinstance(data, dict) else None)
        if not isinstance(rows, list):
            raise SourceError("unexpected response shape")
        out = []
        for m in rows:
            if not isinstance(m, dict):
                continue
            names = _maybe_json_list(m.get("outcomes"))
            prices = _maybe_json_list(m.get("outcomePrices"))
            outcomes = []
            for i, nm in enumerate(names):
                price = _to_float(prices[i]) if i < len(prices) else None
                outcomes.append({"name": str(nm), "norm": normalize_team(str(nm)), "price": price})
            question = m.get("question") or m.get("title") or ""
            out.append(
                {
                    "question": question,
                    "norm_question": normalize_team(question),
                    "slug": m.get("slug"),
                    "condition_id": _first(m, "conditionId", "condition_id"),
                    "outcomes": outcomes,
                    "end_date": _first(m, "endDate", "end_date"),
                }
            )
        return out

    # -- leaderboard ----------------------------------------------------------
    async def fetch_leaderboard(self, limit: int = 12) -> list[dict[str, Any]]:
        url = f"{self.cfg.leaderboard_url}/leaderboard"
        params = {"window": "all", "limit": str(limit), "orderBy": "pnl"}
        data = await self.http.get_json(url, params=params)
        rows = data if isinstance(data, list) else (data.get("data") if isinstance(data, dict) else None)
        if not isinstance(rows, list):
            raise SourceError("unexpected response shape")
        traders = []
        for i, r in enumerate(rows[:limit]):
            if not isinstance(r, dict):
                continue
            addr = _first(r, "proxyWallet", "wallet", "address", "user", "account", "proxy_address")
            if not addr:
                continue
            traders.append(
                {
                    "rank": i + 1,
                    "address": str(addr),
                    "display": _first(r, "name", "pseudonym", "displayName", "username"),
                    "pnl": _to_float(_first(r, "amount", "pnl", "profit", "realizedPnl", "p")),
                    "volume": _to_float(_first(r, "volume", "vol", "totalVolume")),
                }
            )
        return traders

    # -- positions ------------------------------------------------------------
    async def fetch_positions(self, address: str) -> list[dict[str, Any]]:
        """A trader's currently-open positions (already taken). Defensive parse."""
        url = f"{self.cfg.data_url}/positions"
        params = {"user": address, "sizeThreshold": "1"}
        data = await self.http.get_json(url, params=params)
        rows = data if isinstance(data, list) else (data.get("data") if isinstance(data, dict) else None)
        if not isinstance(rows, list):
            raise SourceError("unexpected response shape")
        positions = []
        for p in rows:
            if not isinstance(p, dict):
                continue
            title = _first(p, "title", "marketTitle", "question", "market", default="")
            positions.append(
                {
                    "market_title": str(title),
                    "norm_title": normalize_team(str(title)),
                    "slug": _first(p, "slug", "eventSlug", "marketSlug"),
                    "condition_id": _first(p, "conditionId", "condition_id", "market", "asset"),
                    "outcome": _first(p, "outcome", "outcomeName", "side"),
                    "size": _to_float(_first(p, "size", "shares", "quantity")),
                    "avg_price": _to_float(_first(p, "avgPrice", "averagePrice", "avg_price")),
                    "cur_price": _to_float(_first(p, "curPrice", "currentPrice", "cur_price", "price")),
                    "value_usd": _to_float(_first(p, "currentValue", "value", "valueUsd", "initialValue")),
                    "unrealized_pnl": _to_float(_first(p, "cashPnl", "unrealizedPnl", "pnl", "cash_pnl")),
                }
            )
        return positions


def match_market_to_fixture(
    home_name: str, away_name: str, markets: list[dict[str, Any]]
) -> Optional[dict[str, Any]]:
    """Find a Polymarket market whose outcomes name BOTH teams (a 3-way match
    market) and map prices to home/draw/away. Returns None if none found."""
    hn, an = normalize_team(home_name), normalize_team(away_name)
    if not hn or not an:
        return None
    for m in markets:
        norms = [o["norm"] for o in m["outcomes"]]
        has_home = any(hn in n or n in hn for n in norms if n)
        has_away = any(an in n or n in an for n in norms if n)
        if not (has_home and has_away):
            continue
        home_pct = draw_pct = away_pct = None
        for o in m["outcomes"]:
            n, price = o["norm"], o["price"]
            if price is None:
                continue
            if n in ("draw", "tie"):
                draw_pct = price
            elif hn in n or n in hn:
                home_pct = price
            elif an in n or n in an:
                away_pct = price
        if home_pct is None and away_pct is None:
            continue
        return {
            "slug": m.get("slug"),
            "home_pct": round(home_pct, 4) if home_pct is not None else None,
            "draw_pct": round(draw_pct, 4) if draw_pct is not None else None,
            "away_pct": round(away_pct, 4) if away_pct is not None else None,
        }
    return None


def is_world_cup_position(pos: dict[str, Any], wc_terms: tuple[str, ...], wc_condition_ids: set[str]) -> bool:
    """A position counts as World Cup if its market matches a known WC market
    (by condition id) or its title contains a WC query term."""
    cid = pos.get("condition_id")
    if cid and str(cid) in wc_condition_ids:
        return True
    title = (pos.get("market_title") or "").lower()
    slug = (pos.get("slug") or "").lower()
    return any(term in title or term in slug for term in wc_terms)
