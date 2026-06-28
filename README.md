# World Cup 2026 — Prediction & Betting-Market Dashboard

A live dashboard for the **2026 FIFA World Cup** (48 teams; hosted across the
USA, Canada & Mexico; Jun 11 – Jul 19, 2026). It aggregates fixtures and live
scores, runs a transparent win-probability model, compares that model against
real betting markets, and surfaces what top public Polymarket traders have
**already** bet on the tournament.

> ### ⓘ Information only — not betting advice
> Everything here is a **statistical model estimate** or **public market data**,
> shown for information only. It is **not** betting advice, financial advice, or
> a guaranteed outcome. Probabilities are uncertain estimates shown with
> confidence bands. This is a data-aggregation and probability-display tool, not
> an oracle. The app **never places bets** and **never handles money** — there
> is no code path that can.

All tournament data is **fetched live at runtime** — nothing about matches,
scores, odds, or positions is hardcoded. If a source is unavailable, the UI
shows a visible "data unavailable" state rather than inventing numbers.

---

## What it shows (features)

1. **Fixtures & live scores** — schedule, in-progress matches (live score +
   approximate minute), and finished results, from a football data API.
2. **Win-probability model** — pre-match and in-match win / draw / loss %
   computed from **Elo ratings** (built by replaying real results) + **recent
   form**, plus the **live score & minute** when a match is in play. Each
   estimate ships with an explicit **confidence band**, a "Model estimate, not a
   guarantee" label, and the 2–3 input factors driving it.
3. **Odds aggregation** — for each match, a table of **Model %** vs **Sportsbook
   implied %** (vig removed) vs **Polymarket %**. Rows where the model
   materially exceeds the market are flagged as an informational **value edge**.
4. **Smart-money tracker** — Polymarket's public leaderboard (top traders by
   P&L / volume) and each tracked trader's **currently open** World Cup
   positions. Only already-taken, public positions are shown; traders with none
   show "no current position." Future bets are never predicted or fabricated.
5. **Single auto-refreshing dashboard** — match cards, model-vs-market tables,
   value flags, and a smart-money panel. Polls without a full reload;
   mobile-responsive; persistent disclaimer.

---

## Stack & layout

Backend: **Python + FastAPI + httpx + APScheduler + SQLite**.
Frontend: **React + Vite + Tailwind + TypeScript**.

```
.
├── backend/                  # FastAPI app (python -m backend)
│   ├── config.py             # .env-driven config (keys, URLs, model params)
│   ├── http_client.py        # async HTTP w/ retries + typed SourceError
│   ├── db.py                 # SQLite: response cache, Elo, source health, snapshots
│   ├── models.py             # Pydantic API contract (+ persistent DISCLAIMER)
│   ├── service.py            # aggregation: fetch → model → compare → snapshot
│   ├── server.py             # routes + APScheduler refresh loop
│   ├── sources/
│   │   ├── football.py       # football-data.org: schedule, scores, form, lineups
│   │   ├── odds.py           # the-odds-api.com: H2H odds → de-vigged implied %
│   │   └── polymarket.py     # gamma (prices) + lb-api (leaderboard) + data-api (positions)
│   └── winprob/
│       ├── elo.py            # World-Football-Elo built from real finished matches
│       └── model.py          # Poisson/Skellam W/D/L, pre-match & in-match, bands
├── frontend/                 # React + Vite + Tailwind dashboard
│   └── src/{App.tsx, api.ts, hooks/, components/, lib/}
├── scripts/smoke_test.py     # offline model-math + graceful-degradation checks
├── requirements.txt          # backend deps
└── .env.example              # copy to .env and fill in keys
```

---

## Setup

### 1. Backend (Python 3.10+)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. API keys

```bash
cp .env.example .env      # then edit .env
```

| Variable | Required for | Where to get it | Free tier? |
|----------|--------------|-----------------|------------|
| `FOOTBALL_DATA_API_KEY` | Fixtures, live scores, the model | https://www.football-data.org/client/register | Yes — includes the World Cup competition, but rate limited (~10 req/min) |
| `THE_ODDS_API_KEY` | Sportsbook odds + value flags | https://the-odds-api.com/ | Yes — ~500 req/month |
| *(Polymarket)* | Prediction-market odds, leaderboard, positions | no key — public APIs | n/a |

The app **boots with zero keys** — each unconfigured or unreachable source just
renders "data unavailable." Keys are read only from `.env`; nothing is hardcoded.

### 3. Frontend (Node 18+)

```bash
cd frontend && npm install
```

---

## Running

From the repo root with the venv active:

```bash
python -m backend            # FastAPI backend on http://127.0.0.1:8000
# in another terminal:
cd frontend && npm run dev   # dashboard on http://localhost:5173 (proxies /api)
```

Open **http://localhost:5173**. The dashboard polls `/api/dashboard` every ~12s;
the backend recomputes in the background (≈60s while matches are live, every 6h
otherwise) so the page always reflects the freshest stored snapshot.

**Single-process option:** `cd frontend && npm run build`, then `python -m
backend` — the backend serves the built `frontend/dist` at `/` (so just open
http://127.0.0.1:8000).

### Quick offline check (no network/keys needed)

```bash
python -m scripts.smoke_test
```

Validates the Elo + win-probability math (e.g. a team leading late flips the
favorite; missing inputs yield *no* estimate) and that a full refresh degrades
cleanly with the persistent disclaimer intact.

---

## How the model works

* **Elo** is not hardcoded — every team starts at a neutral 1500 and ratings are
  built by replaying the real **finished** matches fetched from the football API,
  in date order, using the World-Football-Elo update (with a margin-of-victory
  multiplier). Few matches played ⇒ a **provisional** rating (marked `*`) and a
  **wider** confidence band.
* **Recent form** (points/game over the last up-to-5 results) nudges the rating
  edge.
* The rating edge maps to an **expected-goals** rate per team; final-score
  outcome probabilities come from a **Poisson/Skellam** goal model. Pre-match
  uses full-match rates; **in-match** uses the current score plus goals expected
  over the *remaining* time, so a late lead correctly dominates the estimate.
* Each card shows **Model estimate, not a guarantee**, the band (±%), the basis
  (pre-match / in-match), and the driving factors.

**Value edge** = `model % − sportsbook implied %` for an outcome. A row is
flagged when that edge clears `VALUE_EDGE_THRESHOLD` (default 5 pts). It is an
informational signal about where the model and book disagree — **not advice**.

---

## Data-source limitations (plain English)

* **football-data.org (fixtures/scores/model).** The free tier covers the World
  Cup but is **rate limited** and does **not** expose a precise live match clock,
  so the **live minute is an approximation** derived from kickoff time (labelled
  "~"). **Lineups** are best-effort and often empty on the free plan; the card
  only shows them when the API returns them. Elo/form are built purely from
  tournament results, so early in the tournament ratings are provisional and the
  model reports wide bands.
* **the-odds-api.com (sportsbook odds).** Free tier is **~500 requests/month**,
  so the app refreshes odds on the slow (6h) cadence, not every 60s, to conserve
  quota. Odds are matched to fixtures by team name; an unusual name spelling can
  occasionally leave a match without a market ("No matching market found").
* **Polymarket (odds / leaderboard / positions).** All public, no key. Per-match
  prices are matched **best-effort** to 3-way match markets by team name — many
  matches won't have a dedicated Polymarket market, so the "Poly" column may be
  blank. Leaderboard and positions endpoint shapes can change over time; the
  parsers are defensive and fall back to "data unavailable." Positions shown are
  **only** what a trader already holds — the app never infers or predicts a
  trader's future bets (that data does not exist).
* **General.** Any failed source falls back to the last cached value (flagged
  stale) or, if never seen, a visible "data unavailable" chip. Numbers are never
  invented.

> **Network note:** the dashboard needs outbound HTTPS to the data providers. In
> a locked-down/no-egress environment every source will correctly show "data
> unavailable" — run it somewhere the APIs are reachable, with keys set in
> `.env`, to see live data.

---

## API reference (backend)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | liveness; which sources are configured; refresh cadence |
| GET | `/api/dashboard` | latest snapshot: matches, model, market, value flags, smart money |
| GET | `/api/sources` | per-source health (ok / detail / last-ok time) |
| POST | `/api/refresh` | force a full (baseline) refresh now |

---

## Configuration

All tuning is optional via `.env` (see `.env.example` for the full list):
`REFRESH_LIVE_SECONDS` (60), `REFRESH_BASELINE_SECONDS` (21600 / 6h),
`VALUE_EDGE_THRESHOLD` (0.05), `ELO_K_FACTOR` (40), `DB_PATH`, `CORS_ORIGINS`,
plus base-URL overrides for each provider.
