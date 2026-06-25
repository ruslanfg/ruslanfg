"""On-chain Polygon trader tracking via CTF Exchange fills (secondary source).

Reconstructs fills from ``OrderFilled`` logs on the standard CTF Exchange using
raw JSON-RPC ``eth_getLogs`` (no web3 dependency required — pure ABI decoding),
so it degrades gracefully. Handles the 2026-04-28 V2 migration by switching the
decoder on topic0.

This is READ-ONLY log scanning. It never signs or sends anything.

Verified addresses / topic0s (Polygon chainId 137):
  * CTF Exchange V1  0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E
  * CTF Exchange V2  0xE111180000d2663C0091e4f400237545B87B996B  (current)
  * V1 OrderFilled topic0 0xd0a08e8c493f9c94f29311604c9de1b4e8c8d4c06bd0c789af57f2d65bfec0f6
  * V2 OrderFilled topic0 0xd543adfd945773f1a62f74f0ee55a5e3b9b1a28262980ba90b1a89f2ea84d8ee
Amounts are 6-decimal base units (1e6 = $1 collateral = 1 share) for both legs.
"""
from __future__ import annotations

from typing import Optional

from ..config import Config
from ..logging_setup import get_logger
from ..models import ObservedTrade
from .base import HttpClient

log = get_logger("sources.onchain")

CTF_EXCHANGE_V1 = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
CTF_EXCHANGE_V2 = "0xE111180000d2663C0091e4f400237545B87B996B"
ORDERFILLED_V1 = "0xd0a08e8c493f9c94f29311604c9de1b4e8c8d4c06bd0c789af57f2d65bfec0f6"
ORDERFILLED_V2 = "0xd543adfd945773f1a62f74f0ee55a5e3b9b1a28262980ba90b1a89f2ea84d8ee"
SCALE = 1_000_000  # 1e6 base units


def _addr_from_topic(topic: str) -> str:
    return "0x" + topic[-40:]


def _words(data_hex: str) -> list[int]:
    h = data_hex[2:] if data_hex.startswith("0x") else data_hex
    return [int(h[i:i + 64], 16) for i in range(0, len(h) - len(h) % 64, 64)]


class OnchainClient:
    def __init__(self, cfg: Config, http: HttpClient):
        self.cfg = cfg
        self.http = http
        self.rpc = (cfg.data.polygon_rpc_url or "").strip()

    @property
    def configured(self) -> bool:
        return bool(self.rpc)

    async def _rpc(self, method: str, params: list) -> Optional[object]:
        if not self.configured:
            return None
        try:
            resp = await self.http.post_json(
                self.rpc, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            )
            if isinstance(resp, dict) and "result" in resp:
                return resp["result"]
            log.debug("rpc %s error: %s", method, resp)
        except Exception as exc:  # noqa: BLE001
            log.debug("rpc %s failed: %s", method, exc)
        return None

    async def block_number(self) -> Optional[int]:
        res = await self._rpc("eth_blockNumber", [])
        return int(res, 16) if isinstance(res, str) else None

    def _decode_log(self, lg: dict, token_filter: set[str] | None) -> Optional[ObservedTrade]:
        topics = lg.get("topics") or []
        if len(topics) < 4:
            return None
        topic0 = topics[0].lower()
        maker = _addr_from_topic(topics[2])
        words = _words(lg.get("data", "0x"))
        tx = lg.get("transactionHash")

        if topic0 == ORDERFILLED_V2 and len(words) >= 5:
            side = words[0]                       # 0=BUY, 1=SELL
            token_id = str(words[1])
            maker_amt, taker_amt = words[2], words[3]
            if side == 0:                          # BUY: pay collateral, get shares
                collateral, shares = maker_amt, taker_amt
                trade_side = "BUY"
            else:                                  # SELL: give shares, get collateral
                shares, collateral = maker_amt, taker_amt
                trade_side = "SELL"
        elif topic0 == ORDERFILLED_V1 and len(words) >= 5:
            maker_asset, taker_asset = words[0], words[1]
            maker_amt, taker_amt = words[2], words[3]
            if maker_asset == 0:                   # maker paid collateral → BUY
                collateral, shares, token_id = maker_amt, taker_amt, str(taker_asset)
                trade_side = "BUY"
            else:                                  # maker sold outcome token → SELL
                shares, collateral, token_id = maker_amt, taker_amt, str(maker_asset)
                trade_side = "SELL"
        else:
            return None

        if token_filter is not None and token_id not in token_filter:
            return None
        if shares == 0:
            return None
        price = max(0.0, min(1.0, collateral / shares))
        return ObservedTrade(
            wallet=maker, condition_id=None, token_id=token_id, outcome=None,
            side=trade_side, price=round(price, 4), size=shares / SCALE,
            timestamp=0, tx_hash=tx, source="onchain",
        )

    async def fetch_fills(
        self, token_ids: list[str] | None, lookback_blocks: int = 250
    ) -> list[ObservedTrade]:
        """Scan recent OrderFilled logs on V1+V2 exchanges; optional token filter."""
        latest = await self.block_number()
        if latest is None:
            return []
        from_block = max(0, latest - lookback_blocks)
        params = [{
            "address": [CTF_EXCHANGE_V1, CTF_EXCHANGE_V2],
            "topics": [[ORDERFILLED_V1, ORDERFILLED_V2]],
            "fromBlock": hex(from_block),
            "toBlock": hex(latest),
        }]
        logs = await self._rpc("eth_getLogs", params)
        if not isinstance(logs, list):
            return []
        token_filter = set(token_ids) if token_ids else None
        out: list[ObservedTrade] = []
        for lg in logs:
            if lg.get("removed"):  # reorged
                continue
            try:
                t = self._decode_log(lg, token_filter)
            except Exception:  # noqa: BLE001
                t = None
            if t:
                out.append(t)
        return out

    async def health(self) -> tuple[bool, str]:
        if not self.configured:
            return False, "no POLYGON_RPC_URL configured"
        bn = await self.block_number()
        if bn is None:
            return False, "RPC unreachable"
        return True, f"polygon block {bn}"
