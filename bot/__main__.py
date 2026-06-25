"""CLI entrypoint.

  python -m bot              # run the paper-trading loop (Definition of Done)
  python -m bot run         #    … same thing, explicit
  python -m bot probe       # check which data sources return data vs fail
  python -m bot cycle       # walk through ONE full simulated trade cycle, end to end
  python -m bot serve       # run the FastAPI backend only
  python -m bot all         # run loop + backend together (one process, for the dashboard)
"""
from __future__ import annotations

import argparse
import asyncio
import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import load_config
from .db import Database
from .engine import PaperEngine
from .logging_setup import setup_logging, get_logger
from .loop import Bot
from .models import UP
from .sources.sim import SimProvider
from .wallets import rank_wallets, top_wallet_addresses

console = Console()
log = get_logger("cli")


def _open(cfg):
    return Database(cfg.storage.db_path)


# --------------------------------------------------------------------------- #
# probe — Step 1 review: which sources returned data vs failed
# --------------------------------------------------------------------------- #
async def cmd_probe(cfg) -> None:
    from .sources.live import LiveProvider
    db = _open(cfg)
    console.print(Panel.fit("[bold]Data-source probe[/bold] — Polymarket BTC 5-min paper bot",
                            border_style="cyan"))
    live = LiveProvider(cfg, db)
    console.print("[dim]Probing live sources (Gamma, CLOB, Data API, on-chain)…[/dim]")
    statuses = await live.health_check()
    await live.aclose()

    table = Table(show_header=True, header_style="bold")
    table.add_column("Source")
    table.add_column("Status")
    table.add_column("Detail / Error", overflow="fold")
    for s in statuses:
        status = "[green]✓ returned data[/green]" if s.ok else "[red]✗ failed[/red]"
        table.add_row(s.name, status, (s.detail or s.error or ""))
    # Simulator is always available.
    sim = SimProvider(cfg)
    sim_stat = (await sim.health_check())[0]
    table.add_row("simulator", "[green]✓ available[/green]", sim_stat.detail)
    console.print(table)

    any_live = any(s.ok for s in statuses)
    if any_live:
        console.print("[green]auto mode → would use LIVE provider.[/green]")
    else:
        console.print(Panel(
            "All live Polymarket/Polygon sources are unreachable from here "
            "(likely network egress policy). [bold]auto mode → falls back to the "
            "deterministic simulator[/bold], and the gap is logged. Run on a host with "
            "open internet (or allowlist the Polymarket hosts) for live data.",
            border_style="yellow", title="network gap"))
    db.close()


# --------------------------------------------------------------------------- #
# cycle — Step 2 review: one full simulated trade cycle, end to end
# --------------------------------------------------------------------------- #
async def cmd_cycle(cfg) -> None:
    db = _open(cfg)
    console.print(Panel.fit("[bold]One full simulated trade cycle[/bold] (end to end)",
                            border_style="magenta"))

    # Controllable clock so we can fast-forward through a whole 5-min window.
    clk = {"t": time.time()}
    provider = SimProvider(cfg, clock=lambda: clk["t"])

    # Pick a clean upcoming window we fully control.
    w = provider.window_index(time.time()) + 1
    start = provider.window_start(w)
    tick = provider.tick

    clk["t"] = start + 1
    console.print(f"[dim]Seeding {cfg.wallets.lookback_days}d of synthetic history & ranking wallets…[/dim]")
    provider.bootstrap_history(db, cfg.wallets.lookback_days)
    rank_wallets(db, cfg)

    bot = Bot(cfg, db)
    bot.provider = provider
    bot._last_poll = start - 1
    bot._last_rank = int(clk["t"])

    engine: PaperEngine = bot.engine
    eq_before = engine.equity
    cash_before = engine.cash

    top = sorted(top_wallet_addresses(db, cfg))
    console.print(f"\n[bold]1) Tracked top-{cfg.wallets.top_n} wallets[/bold] (by score):")
    tw = Table(show_header=True, header_style="bold")
    for c in ("rank", "wallet", "win_rate", "realized_pnl", "trades", "score"):
        tw.add_column(c)
    for row in db.top_wallets(cfg.wallets.top_n, cfg.wallets.min_trades):
        tw.add_row(str(row["rank"]), row["wallet"][:14] + "…",
                   f"{row['win_rate']*100:.1f}%", f"${row['realized_pnl']:.2f}",
                   str(row["trades_count"]), f"{row['score']:.3f}")
    console.print(tw)

    clk["t"] = start + int(tick * 0.25)
    market = await provider.discover_market()
    console.print(f"\n[bold]2) Active market[/bold]: {market.condition_id} "
                  f"[dim]({market.question})[/dim]")
    console.print(f"   window {start}–{start+tick} | open=${market.raw['open']:,.2f} "
                  f"close=${market.raw['close']:,.2f} → resolves "
                  f"[bold]{'UP' if market.raw['close']>=market.raw['open'] else 'DOWN'}[/bold]")
    up_q = await provider.get_quote(market.up_token_id)
    console.print(f"   live quote UP token: bid={up_q.best_bid} ask={up_q.best_ask}")

    # Poll several times across the window (like the real 15s loop) to catch
    # top-wallet entries as they arrive, mirroring at the then-current quote.
    seen, mirrored = 0, 0
    for frac in (0.25, 0.5, 0.75):
        clk["t"] = start + int(tick * frac)
        rep = await bot.run_once()
        seen += rep.new_trades
        mirrored += rep.mirrored
    console.print(f"\n[bold]3) Mirror step[/bold] (3 polls across the window): "
                  f"{seen} tracked-wallet trades seen, "
                  f"[green]{mirrored} mirrored[/green] as paper positions.")
    opened = db.open_positions()
    tp = Table(show_header=True, header_style="bold", title="Open paper positions")
    for c in ("id", "outcome", "entry", "shares", "$size", "copied wallet"):
        tp.add_column(c)
    for p in opened:
        tp.add_row(str(p["id"]), p["outcome"], f"{p['entry_price']:.3f}",
                   f"{p['shares']:.2f}", f"${p['size_usd']:.2f}",
                   (p["source_wallet"] or "")[:14] + "…")
    console.print(tp)

    # Fast-forward past the window close → auto-resolution & settlement.
    clk["t"] = start + tick + 2
    console.print(f"\n[bold]4) Fast-forward to window close[/bold] (t={clk['t']:.0f}); "
                  "market resolves via simulated outcome…")
    repB = await bot.run_once()
    console.print(f"   resolved: [bold]{(await provider.fetch_resolution(market))}[/bold]; "
                  f"[green]{repB.settled} positions settled[/green].")

    tc = Table(show_header=True, header_style="bold", title="Closed positions (this cycle)")
    for c in ("id", "outcome", "resolved", "entry", "exit", "pnl"):
        tc.add_column(c)
    for p in db.closed_positions(limit=len(opened) or 10):
        tc.add_row(str(p["id"]), p["outcome"], p["resolved_outcome"] or "",
                   f"{p['entry_price']:.3f}", f"{p['exit_price']:.2f}",
                   f"[{'green' if (p['pnl'] or 0)>=0 else 'red'}]{p['pnl']:+.2f}[/]")
    console.print(tc)

    console.print(Panel(
        f"bankroll/equity: [bold]${eq_before:,.2f}[/bold] → "
        f"[bold]${engine.equity:,.2f}[/bold]   "
        f"(cash ${cash_before:,.2f} → ${engine.cash:,.2f}, "
        f"realized PnL ${engine.realized_pnl:+,.2f})",
        title="5) Bankroll update", border_style="green"))
    db.close()


# --------------------------------------------------------------------------- #
# run / serve / all
# --------------------------------------------------------------------------- #
async def cmd_run(cfg) -> None:
    db = _open(cfg)
    bot = Bot(cfg, db)
    try:
        await bot.run_forever()
    finally:
        db.close()


def cmd_serve(cfg) -> None:
    import uvicorn
    from .api.server import create_app
    app = create_app(cfg)
    uvicorn.run(app, host=cfg.api.host, port=cfg.api.port, log_level=cfg.logging.level.lower())


async def cmd_all(cfg) -> None:
    import uvicorn
    from .api.server import create_app
    db = _open(cfg)
    bot = Bot(cfg, db)
    app = create_app(cfg)
    server = uvicorn.Server(uvicorn.Config(
        app, host=cfg.api.host, port=cfg.api.port, log_level=cfg.logging.level.lower()))
    loop_task = asyncio.create_task(bot.run_forever())
    try:
        await server.serve()
    finally:
        bot.stop()
        await loop_task
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="bot", description="Polymarket BTC 5-min paper-trading bot")
    parser.add_argument("command", nargs="?", default="run",
                        choices=["run", "probe", "cycle", "serve", "all"])
    parser.add_argument("--config", default=None, help="path to config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    setup_logging(cfg.logging.level, cfg.logging.file, cfg.logging.json)

    if args.command == "probe":
        asyncio.run(cmd_probe(cfg))
    elif args.command == "cycle":
        asyncio.run(cmd_cycle(cfg))
    elif args.command == "serve":
        cmd_serve(cfg)
    elif args.command == "all":
        try:
            asyncio.run(cmd_all(cfg))
        except KeyboardInterrupt:
            pass
    else:  # run
        try:
            asyncio.run(cmd_run(cfg))
        except KeyboardInterrupt:
            console.print("\n[yellow]stopped[/yellow]")


if __name__ == "__main__":
    main()
