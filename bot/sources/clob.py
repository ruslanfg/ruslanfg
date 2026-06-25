"""CLOB API client — live prices & authoritative resolution.

Base: https://clob.polymarket.com (public, no auth). Everything keys off
``token_id`` (the long decimal-string ERC-1155 asset id from Gamma clobTokenIds).

Verified gotchas handled here:
  * CLOB is snake_case (token_id, tick_size, neg_risk, minimum_tick_size).
  * /price?side=BUY returns the best ASK; side=SELL returns the best BID.
  * /book ordering is unreliable → best_bid = max(bid prices), best_ask = min(ask prices).
  * /book can be stale (0.99/0.01) → prefer /price for top-of-book.
  * /markets/{condition_id} → tokens[].winner is the authoritative resolution signal.
  * All numbers come back as STRINGS → cast with float().
"""
from __future__ import annotations

from typing import Any, Optional

from ..config import Config
from ..logging_setup import get_logger
from ..models import DOWN, UP, Quote
from .base import HttpClient

log = get_logger("sources.clob")


def _f(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class ClobClient:
    def __init__(self, cfg: Config, http: HttpClient):
        self.cfg = cfg
        self.http = http
        self.base = cfg.data.clob_base_url.rstrip("/")

    async def ok(self) -> bool:
        try:
            await self.http.get_json(f"{self.base}/ok")
            return True
        except Exception:  # noqa: BLE001
            # Some deployments only answer on '/'; treat any 2xx-ish as alive.
            try:
                await self.http.get_json(f"{self.base}/")
                return True
            except Exception:  # noqa: BLE001
                return False

    async def get_price(self, token_id: str, side: str) -> Optional[float]:
        """side=BUY → best ask; side=SELL → best bid."""
        try:
            data = await self.http.get_json(
                f"{self.base}/price", {"token_id": token_id, "side": side}
            )
            return _f(data.get("price")) if isinstance(data, dict) else None
        except Exception as exc:  # noqa: BLE001
            log.debug("clob get_price failed: %s", exc)
            return None

    async def get_book_quote(self, token_id: str) -> Optional[Quote]:
        try:
            data = await self.http.get_json(f"{self.base}/book", {"token_id": token_id})
        except Exception as exc:  # noqa: BLE001
            log.debug("clob get_book failed: %s", exc)
            return None
        if not isinstance(data, dict):
            return None
        bids = [b for b in (_f(x.get("price")) for x in data.get("bids", []) or []) if b is not None]
        asks = [a for a in (_f(x.get("price")) for x in data.get("asks", []) or []) if a is not None]
        return Quote(
            token_id=token_id,
            best_bid=max(bids) if bids else None,
            best_ask=min(asks) if asks else None,
        )

    async def get_quote(self, token_id: str) -> Optional[Quote]:
        """Top-of-book; prefers /price (BUY=ask, SELL=bid), falls back to /book."""
        ask = await self.get_price(token_id, "BUY")
        bid = await self.get_price(token_id, "SELL")
        if ask is not None or bid is not None:
            return Quote(token_id=token_id, best_bid=bid, best_ask=ask)
        return await self.get_book_quote(token_id)

    async def get_clob_market(self, condition_id: str) -> Optional[dict]:
        try:
            return await self.http.get_json(f"{self.base}/markets/{condition_id}")
        except Exception as exc:  # noqa: BLE001
            log.debug("clob get_market failed: %s", exc)
            return None

    async def resolution_for(self, condition_id: str, up_token_id: str) -> Optional[str]:
        """Authoritative resolution via tokens[].winner."""
        m = await self.get_clob_market(condition_id)
        if not isinstance(m, dict):
            return None
        tokens = m.get("tokens") or []
        for tok in tokens:
            if tok.get("winner"):
                tid = str(tok.get("token_id"))
                return UP if tid == str(up_token_id) else DOWN
        # Some closed markets expose winner via price≈1 instead of the flag.
        if m.get("closed"):
            for tok in tokens:
                if _f(tok.get("price")) and _f(tok.get("price")) >= 0.99:
                    tid = str(tok.get("token_id"))
                    return UP if tid == str(up_token_id) else DOWN
        return None
