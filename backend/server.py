"""FastAPI app: serves the latest dashboard snapshot and drives the scheduler.

Endpoints:
  GET  /api/health     liveness + which sources are configured
  GET  /api/dashboard  the latest computed snapshot (matches, model, market, etc.)
  GET  /api/sources    source-health detail
  POST /api/refresh    force a full (baseline) refresh now

The dashboard polls /api/dashboard; the APScheduler job recomputes in the
background so requests are always served from the freshest stored snapshot.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import get_config
from .db import Database
from .models import DISCLAIMER
from .service import Aggregator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("worldcup.server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_config()
    db = Database(cfg.db_path)
    agg = Aggregator(cfg, db)
    app.state.cfg = cfg
    app.state.db = db
    app.state.agg = agg

    # Kick off the first full refresh in the background so the server binds
    # immediately; /api/dashboard returns a "warming up" state until it lands.
    async def _warmup():
        try:
            await agg.refresh(force_baseline=True)
        except Exception:  # noqa: BLE001 - never block startup on a data source
            log.exception("initial refresh failed; sources will show as unavailable")

    app.state.warmup = asyncio.create_task(_warmup())

    scheduler = AsyncIOScheduler()

    async def _job():
        try:
            await agg.refresh()
        except Exception:  # noqa: BLE001 - a bad tick must not kill the scheduler
            log.exception("scheduled refresh failed")

    # One adaptive job at the live cadence; it internally throttles the slow
    # sources to the baseline cadence (see Aggregator.tick).
    scheduler.add_job(_job, "interval", seconds=cfg.refresh_live_seconds, id="refresh")
    scheduler.start()
    app.state.scheduler = scheduler
    log.info(
        "started; football=%s odds=%s polymarket=public",
        "configured" if cfg.football.configured else "NO KEY",
        "configured" if cfg.odds.configured else "NO KEY",
    )
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await agg.aclose()
        db.close()


app = FastAPI(title="World Cup 2026 Dashboard API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(get_config().cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    cfg = app.state.cfg
    return {
        "ok": True,
        "disclaimer": DISCLAIMER,
        "sources_configured": {
            "football_data": cfg.football.configured,
            "sportsbook_odds": cfg.odds.configured,
            "polymarket": True,  # public, no key
        },
        "refresh": {
            "live_seconds": cfg.refresh_live_seconds,
            "baseline_seconds": cfg.refresh_baseline_seconds,
        },
    }


@app.get("/api/dashboard")
async def dashboard():
    snap = app.state.db.latest_snapshot()
    if snap is None:
        return JSONResponse(
            {"updated_at": 0, "disclaimer": DISCLAIMER, "matches": [], "sources": [],
             "smart_money": {"available": False, "note": "warming up", "leaderboard": []},
             "live_count": 0, "value_count": 0},
        )
    return snap


@app.get("/api/sources")
async def sources():
    return app.state.db.get_source_statuses()


@app.post("/api/refresh")
async def refresh():
    payload = await app.state.agg.refresh(force_baseline=True)
    return {"ok": True, "updated_at": payload.get("updated_at")}


# --- Optional: serve the built frontend (frontend/dist) for single-process use.
_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")
    log.info("serving built frontend from %s", _DIST)
