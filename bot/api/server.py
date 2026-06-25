"""FastAPI backend: REST endpoints + WebSocket live updates.

The bot loop process writes to SQLite; this API reads from it (WAL-shared) and
pushes periodic snapshots to connected dashboard clients over WebSocket. The
on/off toggle writes ``bot_state.enabled``, which the loop reads each tick.
"""
from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..config import Config, load_config
from ..db import Database
from ..engine import PaperEngine
from ..logging_setup import get_logger
from ..models import Market
from ..provider import build_provider

log = get_logger("api")


# --------------------------------------------------------------------------- #
# serialization helpers
# --------------------------------------------------------------------------- #
def _row(r) -> dict[str, Any]:
    return {k: r[k] for k in r.keys()}


def _market_from_row(row) -> Optional[Market]:
    if not row:
        return None
    return Market(
        condition_id=row["condition_id"], question=row["question"] or "",
        slug=row["slug"] or "", up_token_id=row["up_token_id"] or "",
        down_token_id=row["down_token_id"] or "", start_time=row["start_time"] or 0,
        end_time=row["end_time"] or 0, resolved_outcome=row["resolved_outcome"],
        active=bool(row["active"]), closed=bool(row["closed"]), source=row["source"] or "",
    )


class ToggleRequest(BaseModel):
    enabled: bool


# --------------------------------------------------------------------------- #
# WebSocket connection manager
# --------------------------------------------------------------------------- #
class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: dict) -> None:
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


# --------------------------------------------------------------------------- #
# app factory
# --------------------------------------------------------------------------- #
def create_app(cfg: Config | None = None) -> FastAPI:
    cfg = cfg or load_config()
    app = FastAPI(title="Polymarket BTC 5-min Paper Bot API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    db = Database(cfg.storage.db_path)
    engine = PaperEngine(db, cfg)
    manager = ConnectionManager()
    app.state.cfg = cfg
    app.state.db = db
    app.state.engine = engine
    app.state.provider = None
    app.state.quote_cache = {}

    # ------------------------------------------------------------------ #
    async def get_quote_cached(token_id: str) -> Optional[dict]:
        prov = app.state.provider
        if not prov or not token_id:
            return None
        cache = app.state.quote_cache
        entry = cache.get(token_id)
        if entry and time.time() - entry[0] < 1.5:
            return entry[1]
        try:
            q = await prov.get_quote(token_id)
        except Exception:  # noqa: BLE001
            q = None
        val = {"bid": q.best_bid, "ask": q.best_ask, "mid": q.mid} if q else None
        cache[token_id] = (time.time(), val)
        return val

    def _win_stats() -> dict:
        closed = db.closed_positions(limit=100000)
        total = len(closed)
        wins = sum(1 for p in closed if (p["pnl"] or 0) > 0)
        return {"closed_trades": total, "wins": wins, "losses": total - wins,
                "win_rate": (wins / total) if total else 0.0}

    async def build_snapshot() -> dict:
        market_row = db.latest_market()
        market = _market_from_row(market_row)
        market_dict = None
        if market:
            up_q = await get_quote_cached(market.up_token_id)
            down_q = await get_quote_cached(market.down_token_id)
            secs_left = max(0, (market.end_time or 0) - int(time.time()))
            market_dict = {
                "condition_id": market.condition_id, "question": market.question,
                "slug": market.slug, "start_time": market.start_time,
                "end_time": market.end_time, "seconds_left": secs_left,
                "active": market.active, "closed": market.closed,
                "resolved_outcome": market.resolved_outcome,
                "up": up_q, "down": down_q, "source": market.source,
            }
        stats = _win_stats()
        return {
            "type": "snapshot",
            "updated_at": int(time.time()),
            "mode": cfg.data.mode,
            "enabled": engine.enabled,
            "halted": engine.halted,
            "max_drawdown_pct": cfg.engine.max_drawdown_pct,
            "bankroll": {
                "starting": cfg.engine.starting_bankroll,
                "cash": round(engine.cash, 2),
                "equity": round(engine.equity, 2),
                "realized_pnl": round(engine.realized_pnl, 2),
                "open_exposure": round(engine.open_exposure(), 2),
                "return_pct": round(
                    (engine.equity / cfg.engine.starting_bankroll - 1.0) * 100, 2),
            },
            "stats": stats,
            "open_positions": len(db.open_positions()),
            "market": market_dict,
        }

    # ------------------------------------------------------------------ #
    @app.on_event("startup")
    async def _startup() -> None:
        try:
            app.state.provider = await build_provider(cfg, db)
        except Exception as exc:  # noqa: BLE001
            log.warning("provider unavailable in API (%s); quotes will be omitted", exc)
        app.state.broadcaster = asyncio.create_task(_broadcast_loop())

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        task = getattr(app.state, "broadcaster", None)
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if app.state.provider:
            await app.state.provider.aclose()
        db.close()

    async def _broadcast_loop() -> None:
        while True:
            try:
                if manager.active:
                    await manager.broadcast(await build_snapshot())
            except Exception:  # noqa: BLE001
                log.exception("broadcast error")
            await asyncio.sleep(cfg.api.ws_broadcast_interval_seconds)

    # ------------------------------------------------------------------ #
    # REST endpoints
    # ------------------------------------------------------------------ #
    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True, "mode": cfg.data.mode, "time": int(time.time())}

    @app.get("/api/state")
    async def state() -> dict:
        return await build_snapshot()

    @app.get("/api/positions/open")
    async def positions_open() -> list[dict]:
        out = []
        for p in db.open_positions():
            d = _row(p)
            q = await get_quote_cached(p["token_id"])
            cur = (q.get("mid") if q else None)
            if cur is None:
                cur = p["entry_price"]
            d["current_price"] = cur
            d["current_value"] = round(p["shares"] * cur, 2)
            d["unrealized_pnl"] = round(p["shares"] * cur - p["size_usd"], 2)
            out.append(d)
        return out

    @app.get("/api/positions/closed")
    async def positions_closed(limit: int = 200) -> list[dict]:
        return [_row(p) for p in db.closed_positions(limit=limit)]

    @app.get("/api/wallets")
    async def wallets() -> list[dict]:
        return [_row(w) for w in db.all_wallets()]

    @app.get("/api/market")
    async def market() -> Optional[dict]:
        snap = await build_snapshot()
        return snap["market"]

    @app.get("/api/equity-curve")
    async def equity_curve(limit: int = 1000) -> list[dict]:
        return [_row(r) for r in db.equity_curve(limit=limit)]

    @app.get("/api/sources")
    async def sources() -> list[dict]:
        return [_row(s) for s in db.source_health()]

    @app.post("/api/bot/toggle")
    async def toggle(req: ToggleRequest) -> dict:
        engine.set_enabled(req.enabled)
        snap = await build_snapshot()
        await manager.broadcast(snap)
        return {"enabled": engine.enabled}

    # ------------------------------------------------------------------ #
    # WebSocket
    # ------------------------------------------------------------------ #
    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await manager.connect(ws)
        try:
            await ws.send_json(await build_snapshot())
            while True:
                # We don't require client messages; this keeps the socket open
                # and lets us detect disconnects.
                await ws.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(ws)
        except Exception:  # noqa: BLE001
            manager.disconnect(ws)

    return app


# Module-level app for `uvicorn bot.api.server:app`
app = create_app()
