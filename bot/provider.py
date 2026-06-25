"""Provider factory with live/sim/auto selection.

``auto`` mode probes the live Polymarket/Polygon sources once; if NONE of them
return data (e.g. egress is blocked), it logs the gap and falls back to the
deterministic simulator so the bot still runs end-to-end.
"""
from __future__ import annotations

from .config import Config
from .db import Database
from .logging_setup import get_logger
from .sources.base import Provider
from .sources.sim import SimProvider

log = get_logger("provider")


async def build_provider(cfg: Config, db: Database) -> Provider:
    mode = cfg.data.mode.lower()

    if mode == "sim":
        log.info("data.mode=sim → using deterministic simulator (no network)")
        return SimProvider(cfg)

    # Import the live provider lazily so a missing optional dep (web3) doesn't
    # break sim/auto-fallback.
    try:
        from .sources.live import LiveProvider
    except Exception as exc:  # noqa: BLE001
        log.warning("live provider unavailable (%s)", exc)
        if mode == "live":
            raise
        log.warning("falling back to simulator")
        return SimProvider(cfg)

    live = LiveProvider(cfg, db)

    if mode == "live":
        log.info("data.mode=live → using real Polymarket/Polygon APIs")
        return live

    # auto: probe live; fall back to sim if everything is unreachable.
    log.info("data.mode=auto → probing live sources…")
    statuses = await live.health_check()
    any_ok = any(s.ok for s in statuses)
    for s in statuses:
        log.info("  source %-12s %s%s", s.name, "OK" if s.ok else "FAIL",
                 f" — {s.error}" if (not s.ok and s.error) else "")
    if any_ok:
        log.info("auto → live sources reachable; using LiveProvider")
        return live
    await live.aclose()
    log.warning(
        "auto → ALL live sources unreachable (network gap logged). "
        "Falling back to deterministic simulator."
    )
    return SimProvider(cfg)
