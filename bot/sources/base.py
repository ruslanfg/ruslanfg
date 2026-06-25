"""Provider interface + shared async HTTP helper.

A *provider* gives the engine everything it needs in normalized form:
discover the current market, read quotes, fetch tracked-wallet trades, and read
a market's resolution. Two implementations exist: :class:`LiveProvider`
(real Polymarket/Polygon APIs) and :class:`SimProvider` (deterministic offline).
"""
from __future__ import annotations

import abc
import asyncio
from typing import Any, Optional

import httpx

from ..logging_setup import get_logger
from ..models import Market, ObservedTrade, Quote, SourceStatus

log = get_logger("sources")


class HttpClient:
    """Thin async HTTP/JSON helper with retries and exponential backoff.

    ``trust_env=True`` (the httpx default) means it honours HTTPS_PROXY — so in a
    proxied sandbox a blocked host surfaces as a clean connect error we record,
    rather than a hang.
    """

    def __init__(self, timeout: float = 12.0, max_retries: int = 3, backoff: float = 2.0):
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": "polymarket-btc5m-paperbot/0.1 (read-only)"},
            follow_redirects=True,
        )
        self.max_retries = max_retries
        self.backoff = backoff
        self.force_single = False  # when True, do exactly one attempt (probe mode)

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        """Retry transient errors only; never retry a definitive 4xx (e.g. 403
        policy denial) except 429 rate-limiting."""
        if isinstance(exc, httpx.HTTPStatusError):
            code = exc.response.status_code
            return code == 429 or code >= 500
        return isinstance(exc, (httpx.TransportError, httpx.TimeoutException))

    async def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        last_exc: Exception | None = None
        attempts = 1 if self.force_single else self.max_retries
        for attempt in range(attempts):
            try:
                resp = await self._client.request(method, url, **kwargs)
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:  # noqa: BLE001 - re-raised below
                last_exc = exc
                if attempt < attempts - 1 and self._retryable(exc):
                    await asyncio.sleep(self.backoff * (2 ** attempt))
                else:
                    break
        assert last_exc is not None
        raise last_exc

    async def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        return await self._request("GET", url, params=params)

    async def post_json(self, url: str, payload: dict[str, Any]) -> Any:
        """POST helper (used only for JSON-RPC reads, never for trading)."""
        return await self._request("POST", url, json=payload)

    async def aclose(self) -> None:
        await self._client.aclose()


class Provider(abc.ABC):
    """Abstract market/trader data provider."""

    name: str = "provider"

    @abc.abstractmethod
    async def discover_market(self) -> Optional[Market]:
        """Return the currently-active BTC 5-minute market, or None."""

    @abc.abstractmethod
    async def get_quote(self, token_id: str) -> Optional[Quote]:
        """Top-of-book (best bid/ask) for one outcome token."""

    @abc.abstractmethod
    async def fetch_trades(
        self, condition_ids: list[str] | None, since_ts: int
    ) -> list[ObservedTrade]:
        """Recent trades (for wallet discovery, ranking, and live mirroring)."""

    @abc.abstractmethod
    async def fetch_resolution(self, market: Market) -> Optional[str]:
        """Return 'UP'/'DOWN' once the market has resolved, else None."""

    @abc.abstractmethod
    async def health_check(self) -> list[SourceStatus]:
        """Probe each underlying source; report what returned data vs failed."""

    def now(self) -> int:
        """Provider time source (real wall clock by default; sim overrides)."""
        import time
        return int(time.time())

    async def get_quotes(self, market: Market) -> tuple[Optional[Quote], Optional[Quote]]:
        up = await self.get_quote(market.up_token_id)
        down = await self.get_quote(market.down_token_id)
        return up, down

    async def aclose(self) -> None:  # pragma: no cover - overridden where needed
        pass
