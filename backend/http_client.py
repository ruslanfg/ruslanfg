"""Thin async HTTP/JSON helper with retries, backoff, and clean error typing.

``trust_env=True`` (httpx default) means HTTPS_PROXY is honoured, so a host that
the egress policy blocks surfaces as a clean connect error we can record as
"data unavailable" — never a hang, never invented data.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

log = logging.getLogger("worldcup.http")


class SourceError(Exception):
    """A data source could not be read. Carries a short human-readable reason."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class HttpClient:
    def __init__(self, timeout: float = 15.0, max_retries: int = 3, backoff: float = 1.5):
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": "worldcup-2026-dashboard/0.1 (read-only)"},
            follow_redirects=True,
        )
        self.max_retries = max_retries
        self.backoff = backoff

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        # Retry transient errors only. Never retry a definitive 4xx (e.g. 401 bad
        # key, 403 policy denial) except 429 rate-limiting.
        if isinstance(exc, httpx.HTTPStatusError):
            code = exc.response.status_code
            return code == 429 or code >= 500
        return isinstance(exc, (httpx.TransportError, httpx.TimeoutException))

    @staticmethod
    def _describe(exc: Exception) -> str:
        if isinstance(exc, httpx.HTTPStatusError):
            code = exc.response.status_code
            label = {
                401: "unauthorized (check API key)",
                403: "forbidden (blocked or plan does not cover this)",
                404: "not found",
                429: "rate limited",
            }.get(code, f"HTTP {code}")
            return label
        if isinstance(exc, httpx.TimeoutException):
            return "timed out"
        if isinstance(exc, httpx.TransportError):
            return "network unreachable"
        return str(exc) or exc.__class__.__name__

    async def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = await self._client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:  # noqa: BLE001 - normalized below
                last_exc = exc
                if attempt < self.max_retries - 1 and self._retryable(exc):
                    await asyncio.sleep(self.backoff * (2**attempt))
                else:
                    break
        assert last_exc is not None
        reason = self._describe(last_exc)
        log.warning("GET %s failed: %s", url, reason)
        raise SourceError(reason) from last_exc

    async def aclose(self) -> None:
        await self._client.aclose()
