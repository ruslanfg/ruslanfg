# Polymarket BTC 5‑Minute — Paper‑Trading Copy Bot + Dashboard

A fully automated **paper‑trading** bot that mirrors top on‑chain traders on
Polymarket's recurring **"Bitcoin Up or Down — 5 Minute"** market, plus a
polished React dashboard to monitor it live.

> ### ⚠️ Paper trading only
> This project **never** signs a transaction, **never** handles a wallet key or
> mnemonic, and **never** moves real funds. There is no code path that can. Every
> "fill" is a simulated row in SQLite, priced off the live market's best bid/ask
> plus configurable slippage. The bankroll is virtual.

---

## What it does

1. **Discovers** the currently‑active BTC 5‑minute market on Polymarket (Gamma API,
   deterministic `btc-updown-5m-{window_ts}` slug).
2. **Tracks & ranks wallets** from trade history (Data API `/trades`, optionally
   on‑chain CTF Exchange logs). Each wallet is scored by **win rate × volume‑weighted
   realized PnL** over a configurable lookback (default 7 days, min 20 trades).
   Polymarket exposes a PnL/volume leaderboard but **no win‑rate leaderboard**, so
   win rate is computed locally from graded trades — exactly as the task requires.
3. **Copies** the top‑N wallets: when one enters the live 5‑min market, the bot
   mirrors it as a paper trade (same side, size = a fraction of the current bankroll),
   filling at best ask/bid + slippage.
4. **Auto‑resolves** every paper position at market close using Polymarket's reported
   outcome (CLOB `tokens[].winner`, Chainlink‑settled), updates the bankroll, and
   **rolls over** to the next 5‑minute market automatically.
5. **Serves** a FastAPI backend (REST + WebSocket) that a React/Vite/Tailwind/recharts
   dashboard renders live.

### Live vs. simulated data

The bot has three data modes (`data.mode` in `config.yaml`):

| mode | behaviour |
|------|-----------|
| `live` | only the real Polymarket / Polygon APIs (errors loudly if unreachable) |
| `sim`  | a deterministic, seeded offline simulator — no network at all |
| `auto` | try `live`; if **every** live source is unreachable, **log the gap and fall back to `sim`** (default) |

The simulator implements the full data‑provider interface (markets, quotes,
rollover, resolution, and synthetic tracked wallets with trade histories), so the
loop **and** the dashboard run end‑to‑end anywhere — including restricted networks
where Polymarket egress is blocked. Run `python -m bot probe` to see exactly which
sources are reachable from your machine.

---

## Project layout

```
.
├── config.yaml            # THE single config file — every tunable lives here
├── .env.example           # secrets template (copy to .env) — none are required
├── requirements.txt       # Python deps
├── bot/                   # Python backend
│   ├── __main__.py        # CLI: run | probe | cycle | serve | all
│   ├── config.py          # config.yaml + .env loader
│   ├── db.py              # SQLite schema + access (markets, trades, tracked_wallets,
│   │                      #   paper_positions, paper_fills, bankroll_history, …)
│   ├── models.py          # normalized domain models
│   ├── provider.py        # live/sim/auto provider factory
│   ├── sources/           # gamma, clob, data_api, onchain (live) + sim + base
│   ├── wallets.py         # wallet grading + scoring/ranking
│   ├── engine.py          # paper fills, sizing, settlement, bankroll
│   ├── loop.py            # main poll loop (discover → mirror → resolve → rollover)
│   └── api/server.py      # FastAPI REST + WebSocket
└── dashboard/             # React + Vite + Tailwind + recharts frontend
```

---

## Setup

### 1. Backend (Python 3.10+)

```bash
python -m venv .venv && source .venv/bin/activate     # or: uv venv .venv && source .venv/bin/activate
pip install -r requirements.txt                        # or: uv pip install -r requirements.txt
```

### 2. Environment / secrets

```bash
cp .env.example .env
```

**No API keys are required.** Every Polymarket endpoint the bot reads is public.
The only optional value is a private Polygon RPC URL for on‑chain trader tracking:

| Variable | Required? | Purpose |
|----------|-----------|---------|
| `POLYGON_RPC_URL` | optional | Polygon (chain 137) JSON‑RPC for on‑chain CTF Exchange log scanning. Leave blank to use the public default. On‑chain tracking is **off by default** (`data.enable_onchain: false`). |
| `DB_PATH` | optional | Override the SQLite path. |

> There is intentionally **no** variable for a private key or mnemonic. If you ever
> feel one is needed, stop — this is paper trading.

### 3. Dashboard (Node 18+)

```bash
cd dashboard
npm install
```

---

## Running

All commands run from the repo root with the venv active.

```bash
python -m bot probe     # ✅ Step-1 review: which data sources return data vs fail
python -m bot cycle     # ✅ Step-2 review: walk through ONE full simulated trade cycle
python -m bot run       # run the paper-trading loop (Definition of Done)
python -m bot serve     # run only the FastAPI backend (http://127.0.0.1:8000)
python -m bot all       # run the loop + backend together (best for the dashboard)
python -m bot reset     # wipe paper bankroll/positions/equity for a clean start
```

Then start the dashboard:

```bash
cd dashboard
npm run dev             # http://localhost:5173  (proxies /api and /ws to the backend)
```

`npm run dev` proxies API + WebSocket traffic to `http://127.0.0.1:8000`, so the
two run side by side with no CORS setup. To point at a different backend:
`VITE_BACKEND=http://host:port npm run dev`.

**Typical workflow:** terminal 1 → `python -m bot all`; terminal 2 → `cd dashboard && npm run dev`; open http://localhost:5173.

The loop writes to SQLite (`data/paper_trading.db`); the backend reads from it and
pushes live snapshots over WebSocket. The dashboard's **Start/Stop** button toggles
trading via `bot_state.enabled`, which the loop honours each tick (it keeps polling
but stops opening new positions while paused).

---

## Configuration — `config.yaml`

Every tunable lives in this one file. Secrets are referenced as `${VAR}` and resolved
from `.env`.

### `data`
| key | default | meaning |
|-----|---------|---------|
| `mode` | `auto` | `live` \| `sim` \| `auto` (see table above) |
| `gamma_base_url` / `clob_base_url` / `data_api_base_url` / `ws_url` | Polymarket URLs | API base URLs (public) |
| `polygon_rpc_url` | `${POLYGON_RPC_URL}` | Polygon JSON‑RPC for on‑chain scanning |
| `enable_onchain` | `false` | augment Data API tape with on‑chain CTF Exchange `OrderFilled` logs (read‑only) |
| `poll_interval_seconds` | `5` | main loop cadence |
| `http_timeout_seconds` | `12` | per‑request timeout |
| `max_retries` / `retry_backoff_seconds` | `3` / `1` | transient‑error retry policy (4xx like 403 are **not** retried) |

### `market`
| key | default | meaning |
|-----|---------|---------|
| `asset_symbol` | `BTC` | tracked asset |
| `series_slugs` / `question_contains` | btc up/down hints | fallback matchers for market discovery |
| `duration_minutes` | `5` | market window length / rollover detection |

### `wallets` (trader tracking & ranking)
| key | default | meaning |
|-----|---------|---------|
| `lookback_days` | `7` | history window for grading/scoring |
| `min_trades` | `15` | ignore wallets with fewer graded trades |
| `top_n` | `40` | mirror the top‑N ranked wallets |
| `refresh_interval_seconds` | `300` | how often to re‑rank |
| `max_wallets_tracked` | `200` | cap on the wallet universe |
| `backfill_windows` | `180` | on live startup, backfill this many recent resolved 5‑min markets + trades so the leaderboard populates immediately (0 disables; ignored in sim) |
| `scoring.win_rate_weight` | `0.5` | weight on win rate |
| `scoring.pnl_weight` | `0.4` | weight on (normalized) volume‑weighted PnL |
| `scoring.volume_weight` | `0.1` | weight on raw volume (activity) |
| `scoring.win_rate_exponent` | `1.0` | `>1` punishes low win rate harder |

`score = (wr_w·win_rate^exp + pnl_w·norm(vw_pnl) + vol_w·norm(volume)) / Σweights`

### `engine` (paper trading)
| key | default | meaning |
|-----|---------|---------|
| `starting_bankroll` | `1000.0` | virtual USDC starting equity |
| `bankroll_fraction` | `0.10` | fraction of current bankroll per copied trade |
| `slippage_bps` | `50` | simulated slippage in basis points (50 = 0.50%) |
| `min_position_usd` | `1.0` | skip copied trades smaller than this |
| `max_open_positions` | `50` | cap on simultaneous open positions |
| `max_position_usd` | `500.0` | hard cap per position |
| `max_entry_price` | `0.85` | skip copies priced above this (worst risk/reward longs) |
| `min_entry_price` | `0.0` | skip copies priced below this (0 = off) |
| `max_drawdown_pct` | `0.25` | drawdown circuit breaker: pause new entries if equity falls this far below start (0 = off; auto-resumes on recovery) |
| `mirror_sells` | `false` | only mirror entries (BUYs) when false |

### `sim` (offline simulator)
| key | default | meaning |
|-----|---------|---------|
| `seed` | `1337` | deterministic seed |
| `num_wallets` | `40` | synthetic tracked wallets generated |
| `btc_start_price` | `65000.0` | sim BTC anchor price |
| `btc_volatility_bps` | `8` | per‑window volatility |
| `wallet_trade_rate` | `0.35` | base probability a wallet trades a window |
| `accelerate` / `accelerated_window_seconds` | `true` / `60` | compress the 5‑min window for fast demos |

### `api`
| key | default | meaning |
|-----|---------|---------|
| `host` / `port` | `127.0.0.1` / `8000` | backend bind address |
| `cors_origins` | localhost:5173 | allowed dashboard origins |
| `ws_broadcast_interval_seconds` | `2` | snapshot push cadence |

### `storage` / `logging`
| key | default | meaning |
|-----|---------|---------|
| `storage.db_path` | `data/paper_trading.db` | SQLite file |
| `logging.level` / `logging.file` / `logging.json` | `INFO` / `logs/bot.log` / `false` | logging config |

---

## API reference (backend)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | liveness + mode |
| GET | `/api/state` | full snapshot: bankroll, PnL, stats, current market |
| GET | `/api/positions/open` | open paper positions (with mark‑to‑market) |
| GET | `/api/positions/closed` | closed trade history |
| GET | `/api/wallets` | tracked wallets + scores/ranks |
| GET | `/api/market` | live market state |
| GET | `/api/equity-curve` | equity history (for the chart) |
| GET | `/api/sources` | data‑source health |
| POST | `/api/bot/toggle` | `{ "enabled": bool }` — start/stop the bot |
| WS | `/ws` | live snapshot stream |

---

## Notes on the API contract

Built against a verified‑current (2026) Polymarket contract:
- **Gamma** returns `clobTokenIds`/`outcomes`/`outcomePrices` as **JSON‑encoded strings** (parsed accordingly); index 0 = the "Up"/first token.
- **CLOB** `/book` ordering is unreliable → best bid = `max(bids)`, best ask = `min(asks)`; `/price?side=BUY` is the ask, `side=SELL` is the bid.
- 5‑min markets resolve via **Chainlink** (Up iff close ≥ open), surfaced by CLOB `tokens[].winner`.
- On‑chain decoding handles the **2026‑04‑28 CTF Exchange V2 migration** (switches `OrderFilled` ABI on topic0; standard binary markets settle on the standard exchange, not neg‑risk).

If a source is unreachable, the bot logs the gap and (in `auto`) falls back to the simulator rather than inventing data.
