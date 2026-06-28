"""Aggregation service.

Pulls every source, builds the win-probability model from real results, compares
model vs market, computes value edges, and assembles the smart-money panel —
then stores a single :class:`DashboardSnapshot` the API serves.

Refresh cadence (one adaptive 60s tick):
  * Football (schedule/live scores) is re-fetched every tick WHILE any match is
    live, else only every ``refresh_baseline_seconds`` (default 6h).
  * The slower / quota-limited sources (sportsbook odds, Polymarket markets,
    leaderboard, positions) refresh every ``refresh_baseline_seconds``.
Anything that fails falls back to the last cached value (flagged stale) or, if
never seen, a visible "data unavailable" state. Numbers are never invented.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Optional

from .config import Config
from .db import Database
from .http_client import HttpClient, SourceError
from .models import (
    DISCLAIMER,
    DashboardSnapshot,
    Lineups,
    MarketComparison,
    MatchCard,
    ModelEstimate,
    OutcomeRow,
    Score,
    SmartMoney,
    SourceStatus,
    TeamRef,
    Trader,
    TraderPosition,
    ValueFlag,
)
from .sources.football import FootballSource, recent_form
from .sources.odds import OddsSource, match_odds_to_fixture, normalize_team
from .sources.polymarket import (
    PolymarketSource,
    is_world_cup_position,
    match_market_to_fixture,
)
from .winprob import model as winmodel
from .winprob.elo import build_ratings

log = logging.getLogger("worldcup.service")

CACHE_FOOTBALL = "football_matches"
CACHE_ODDS = "odds_h2h"
CACHE_PM_MARKETS = "pm_markets"
CACHE_PM_LB = "pm_leaderboard"

LEADERBOARD_LIMIT = 12
POSITIONS_TRADERS = 8  # fetch open positions for the top N traders
FINISHED_CAP = 30  # cap finished matches shown


class Aggregator:
    def __init__(self, cfg: Config, db: Database):
        self.cfg = cfg
        self.db = db
        self.http = HttpClient(timeout=cfg.http_timeout_seconds)
        self.football = FootballSource(cfg, self.http)
        self.odds = OddsSource(cfg, self.http)
        self.polymarket = PolymarketSource(cfg, self.http)
        self._lock = asyncio.Lock()
        self._last_baseline = 0.0
        self._statuses: dict[str, dict[str, Any]] = {}

    async def aclose(self) -> None:
        await self.http.aclose()

    # -- fetch-with-cache helper ---------------------------------------------
    async def _fetch(
        self, key: str, label: str, fetch: Callable[[], Awaitable[Any]]
    ) -> tuple[Any, str]:
        """Run a live fetch; on failure fall back to cached payload. Records
        source health. Returns (data_or_None, freshness ∈ live|stale|unavailable)."""
        try:
            data = await fetch()
            self.db.put_cache(key, ok=True, payload=data)
            self.db.set_source_status(key, ok=True, detail="live")
            self._statuses[key] = {"label": label, "ok": True, "detail": "live"}
            return data, "live"
        except SourceError as exc:
            cached = self.db.get_cache(key)
            if cached and cached["ok"] and cached["payload"] is not None:
                detail = f"{exc.reason}; showing cached data"
                self.db.set_source_status(key, ok=False, detail=detail)
                self._statuses[key] = {"label": label, "ok": False, "detail": detail}
                return cached["payload"], "stale"
            self.db.set_source_status(key, ok=False, detail=exc.reason)
            self._statuses[key] = {"label": label, "ok": False, "detail": exc.reason}
            return None, "unavailable"

    # -- main tick ------------------------------------------------------------
    async def tick(self, force_baseline: bool = False) -> dict[str, Any]:
        async with self._lock:
            now = time.time()
            cached_football = self.db.get_cache(CACHE_FOOTBALL)
            any_live = bool(
                cached_football
                and cached_football.get("payload")
                and any(m.get("status") == "live" for m in cached_football["payload"])
            )
            first_run = self._last_baseline == 0.0
            do_baseline = (
                force_baseline
                or first_run
                or (now - self._last_baseline) >= self.cfg.refresh_baseline_seconds
            )
            do_football = any_live or do_baseline

            # --- Football (schedule / live scores) ---
            if do_football:
                matches, _ = await self._fetch(
                    CACHE_FOOTBALL, self.football.label, self.football.fetch_matches
                )
            else:
                matches = cached_football["payload"] if cached_football else None
                if cached_football:
                    self._statuses[CACHE_FOOTBALL] = {
                        "label": self.football.label,
                        "ok": cached_football["ok"],
                        "detail": "cached (idle)",
                    }
            matches = matches or []

            # --- Slow sources (odds, polymarket markets / leaderboard) ---
            if do_baseline:
                odds_events, _ = await self._fetch(
                    CACHE_ODDS, self.odds.label, self.odds.fetch_h2h
                )
                pm_markets, _ = await self._fetch(
                    CACHE_PM_MARKETS, self.polymarket.label, self.polymarket.fetch_markets
                )
                pm_leaderboard, _ = await self._fetch(
                    CACHE_PM_LB,
                    "Polymarket leaderboard",
                    lambda: self.polymarket.fetch_leaderboard(LEADERBOARD_LIMIT),
                )
                self._last_baseline = now
            else:
                odds_events = self._cached_payload(CACHE_ODDS)
                pm_markets = self._cached_payload(CACHE_PM_MARKETS)
                pm_leaderboard = self._cached_payload(CACHE_PM_LB)
                for k, lbl in (
                    (CACHE_ODDS, self.odds.label),
                    (CACHE_PM_MARKETS, self.polymarket.label),
                    (CACHE_PM_LB, "Polymarket leaderboard"),
                ):
                    self._reflect_cached_status(k, lbl)

            odds_events = odds_events or []
            pm_markets = pm_markets or []

            # --- World-Cup-relevant Polymarket markets (for matching + filter) ---
            fixture_norms = set()
            for m in matches:
                fixture_norms.add(normalize_team(m.get("home_name")))
                fixture_norms.add(normalize_team(m.get("away_name")))
            fixture_norms.discard("")
            wc_terms = self.cfg.polymarket.wc_query
            wc_markets = [
                m for m in pm_markets if _market_is_wc(m, fixture_norms, wc_terms)
            ]
            wc_condition_ids = {
                str(m["condition_id"]) for m in wc_markets if m.get("condition_id")
            }

            # --- Elo + form from finished matches ---
            finished = [
                m for m in matches if m.get("status") == "finished"
            ]
            elo = build_ratings(
                finished,
                self.cfg.model.k_factor,
                self.cfg.model.base_rating,
                self.cfg.model.home_field_advantage,
            )
            self.db.upsert_elo(elo.ratings())
            form_cache: dict[str, Any] = {}

            def get_form(team_id: Optional[str]):
                if not team_id:
                    return None
                if team_id not in form_cache:
                    form_cache[team_id] = recent_form(team_id, finished, n=5)
                return form_cache[team_id]

            # --- Build match cards ---
            cards = [
                self._build_card(m, elo, get_form, odds_events, wc_markets)
                for m in matches
            ]
            cards = _order_cards(cards)
            value_count = sum(
                1
                for c in cards
                if c.market
                for row in c.market.outcomes
                if row.value.flagged
            )
            live_count = sum(1 for c in cards if c.status == "live")

            # --- Smart money (leaderboard + open positions) ---
            smart = await self._build_smart_money(
                pm_leaderboard, wc_terms, wc_condition_ids, do_baseline
            )

            snapshot = DashboardSnapshot(
                updated_at=int(now),
                disclaimer=DISCLAIMER,
                sources=self._source_statuses(),
                matches=cards,
                smart_money=smart,
                live_count=live_count,
                value_count=value_count,
            )
            return snapshot.model_dump()

    async def refresh(self, force_baseline: bool = False) -> dict[str, Any]:
        """Run one tick, attach best-effort live lineups, persist, and return it."""
        payload = await self.tick(force_baseline=force_baseline)
        try:
            await self.attach_live_lineups(payload)
        except Exception:  # noqa: BLE001 - lineups are best-effort, never fatal
            log.debug("lineup attach failed", exc_info=True)
        self.db.put_snapshot(payload)
        return payload

    # -- helpers --------------------------------------------------------------
    def _cached_payload(self, key: str) -> Any:
        c = self.db.get_cache(key)
        return c["payload"] if c and c["ok"] else None

    def _reflect_cached_status(self, key: str, label: str) -> None:
        c = self.db.get_cache(key)
        if c:
            self._statuses[key] = {
                "label": label,
                "ok": c["ok"],
                "detail": "cached (refreshes every 6h)" if c["ok"] else (c["error"] or "unavailable"),
            }
        else:
            self._statuses[key] = {"label": label, "ok": False, "detail": "data unavailable"}

    def _source_statuses(self) -> list[SourceStatus]:
        statuses = self.db.get_source_statuses()
        by_name = {s["name"]: s for s in statuses}
        out = []
        for key, info in self._statuses.items():
            s = by_name.get(key, {})
            out.append(
                SourceStatus(
                    name=key,
                    label=info["label"],
                    ok=info["ok"],
                    detail=info["detail"],
                    last_ok_at=s.get("last_ok_at"),
                    checked_at=s.get("checked_at"),
                )
            )
        return out

    def _build_card(
        self,
        m: dict[str, Any],
        elo,
        get_form,
        odds_events: list[dict[str, Any]],
        wc_markets: list[dict[str, Any]],
    ) -> MatchCard:
        base = self.cfg.model.base_rating

        def team_ref(prefix: str) -> tuple[TeamRef, Optional[float], int, Optional[float], int]:
            tid = m.get(f"{prefix}_id")
            name = m.get(f"{prefix}_name", "?")
            rating_info = elo.get(tid) if tid else None
            rating = rating_info["rating"] if rating_info else base
            n_matches = rating_info["matches"] if rating_info else 0
            form = get_form(tid)
            ppg = form["ppg"] if form else None
            form_n = form["n"] if form else 0
            ref = TeamRef(
                id=tid,
                name=name,
                crest=m.get(f"{prefix}_crest"),
                elo=round(rating, 1),
                elo_provisional=n_matches < self.cfg.model.provisional_matches,
                form=form["results"] if form else None,
                form_ppg=ppg,
            )
            return ref, rating, n_matches, ppg, form_n

        home_ref, home_elo, home_n, home_ppg, home_form_n = team_ref("home")
        away_ref, away_elo, away_n, away_ppg, away_form_n = team_ref("away")

        status = m.get("status", "unknown")
        is_live = status == "live"
        score = Score(home=m.get("home_goals"), away=m.get("away_goals"))

        model_dict = winmodel.compute(
            winmodel.ModelInputs(
                home_id=m.get("home_id") or "",
                home_name=home_ref.name,
                away_id=m.get("away_id") or "",
                away_name=away_ref.name,
                home_elo=home_elo,
                away_elo=away_elo,
                home_matches=home_n,
                away_matches=away_n,
                home_ppg=home_ppg,
                away_ppg=away_ppg,
                form_n=min(home_form_n, away_form_n),
                minute=m.get("minute"),
                home_goals=m.get("home_goals"),
                away_goals=m.get("away_goals"),
                is_live=is_live,
            ),
            self.cfg,
        )
        model = ModelEstimate(**model_dict) if model_dict else None

        market = self._build_market(home_ref.name, away_ref.name, model, odds_events, wc_markets)

        return MatchCard(
            id=m["id"],
            status=status,
            utc_date=m.get("utc_date"),
            minute=m.get("minute"),
            minute_approx=m.get("minute_approx", True),
            stage=m.get("stage"),
            group=m.get("group"),
            home=home_ref,
            away=away_ref,
            score=score,
            model=model,
            market=market,
        )

    def _build_market(
        self,
        home_name: str,
        away_name: str,
        model: Optional[ModelEstimate],
        odds_events: list[dict[str, Any]],
        wc_markets: list[dict[str, Any]],
    ) -> Optional[MarketComparison]:
        ev = match_odds_to_fixture(home_name, away_name, odds_events) if odds_events else None
        pm = match_market_to_fixture(home_name, away_name, wc_markets) if wc_markets else None

        sb_home = sb_draw = sb_away = None
        book = None
        if ev:
            if ev.get("flipped"):
                sb_home, sb_away = ev.get("away_pct"), ev.get("home_pct")
            else:
                sb_home, sb_away = ev.get("home_pct"), ev.get("away_pct")
            sb_draw = ev.get("draw_pct")
            books = ev.get("books") or []
            book = (
                f"{ev.get('book_count', 0)} books"
                if ev.get("book_count", 0) > 1
                else (books[0] if books else None)
            )

        pm_home = pm_draw = pm_away = None
        if pm:
            pm_home, pm_draw, pm_away = pm.get("home_pct"), pm.get("draw_pct"), pm.get("away_pct")

        if ev is None and pm is None:
            return MarketComparison(
                outcomes=self._rows(model, None, None, None, None, None, None),
                sportsbook_available=False,
                polymarket_available=False,
                note="No matching market found"
                if (odds_events or wc_markets)
                else "Market data unavailable",
            )

        rows = self._rows(model, sb_home, sb_draw, sb_away, pm_home, pm_draw, pm_away)
        return MarketComparison(
            outcomes=rows,
            sportsbook_available=ev is not None,
            sportsbook_book=book,
            polymarket_available=pm is not None,
            polymarket_slug=pm.get("slug") if pm else None,
        )

    def _rows(
        self,
        model: Optional[ModelEstimate],
        sb_home, sb_draw, sb_away,
        pm_home, pm_draw, pm_away,
    ) -> list[OutcomeRow]:
        threshold = self.cfg.value_edge_threshold
        specs = [
            ("home", "Home win", model.home_win if model else None, sb_home, pm_home),
            ("draw", "Draw", model.draw if model else None, sb_draw, pm_draw),
            ("away", "Away win", model.away_win if model else None, sb_away, pm_away),
        ]
        rows = []
        for key, label, mp, sb, pm in specs:
            value = ValueFlag()
            if mp is not None and sb is not None:
                edge = round(mp - sb, 4)
                value = ValueFlag(edge=edge, flagged=edge >= threshold)
            rows.append(
                OutcomeRow(
                    key=key,
                    label=label,
                    model_pct=round(mp, 4) if mp is not None else None,
                    sportsbook_pct=round(sb, 4) if sb is not None else None,
                    polymarket_pct=round(pm, 4) if pm is not None else None,
                    value=value,
                )
            )
        return rows

    async def _build_smart_money(
        self,
        leaderboard: Optional[list[dict[str, Any]]],
        wc_terms: tuple[str, ...],
        wc_condition_ids: set[str],
        do_baseline: bool,
    ) -> SmartMoney:
        if not leaderboard:
            status = self._statuses.get(CACHE_PM_LB, {})
            return SmartMoney(
                available=False,
                note=status.get("detail") or "Leaderboard data unavailable",
                leaderboard=[],
            )

        # Fetch each tracked trader's CURRENTLY OPEN positions (already taken).
        # Only on baseline refreshes (positions move slowly; conserves calls).
        top = leaderboard[:POSITIONS_TRADERS]
        positions_by_addr: dict[str, Any] = {}
        if do_baseline:
            results = await asyncio.gather(
                *[self._positions_for(t["address"]) for t in top], return_exceptions=False
            )
            for t, res in zip(top, results):
                positions_by_addr[t["address"]] = res
                self.db.put_cache(f"pm_pos:{t['address']}", ok=res is not None, payload=res)
        else:
            for t in top:
                c = self.db.get_cache(f"pm_pos:{t['address']}")
                positions_by_addr[t["address"]] = c["payload"] if c and c["ok"] else None

        traders: list[Trader] = []
        for t in leaderboard:
            addr = t["address"]
            raw_positions = positions_by_addr.get(addr)
            positions: Optional[list[TraderPosition]] = None
            note = None
            if addr in positions_by_addr:
                if raw_positions is None:
                    note = "positions unavailable"
                else:
                    wc_pos = [
                        p
                        for p in raw_positions
                        if is_world_cup_position(p, wc_terms, wc_condition_ids)
                    ]
                    positions = [
                        TraderPosition(
                            market_title=p["market_title"],
                            slug=p.get("slug"),
                            outcome=p.get("outcome"),
                            size=p.get("size"),
                            avg_price=p.get("avg_price"),
                            cur_price=p.get("cur_price"),
                            value_usd=p.get("value_usd"),
                            unrealized_pnl=p.get("unrealized_pnl"),
                        )
                        for p in wc_pos
                    ]
                    if not positions:
                        note = "no current World Cup position"
            else:
                note = "not tracked for positions"
            traders.append(
                Trader(
                    rank=t.get("rank"),
                    address=addr,
                    display=t.get("display"),
                    pnl=t.get("pnl"),
                    volume=t.get("volume"),
                    positions=positions,
                    positions_note=note,
                )
            )

        lb_status = self._statuses.get(CACHE_PM_LB, {})
        note = None if lb_status.get("ok") else lb_status.get("detail")
        return SmartMoney(available=True, note=note, leaderboard=traders)

    async def _positions_for(self, address: str) -> Optional[list[dict[str, Any]]]:
        try:
            return await self.polymarket.fetch_positions(address)
        except SourceError:
            return None

    async def attach_live_lineups(self, payload: dict[str, Any]) -> None:
        """Best-effort: fetch lineups for live matches and attach to the snapshot.
        Never fails the refresh; absent lineups just stay None."""
        live = [c for c in payload.get("matches", []) if c.get("status") == "live"]
        for card in live[:6]:
            lu = await self.football.fetch_lineups(card["id"])
            if lu:
                card["lineups_available"] = True
                card["lineups"] = Lineups(**lu).model_dump()


def _market_is_wc(m: dict[str, Any], fixture_norms: set[str], wc_terms: tuple[str, ...]) -> bool:
    nq = m.get("norm_question") or ""
    if any(term in (m.get("question") or "").lower() or term in (m.get("slug") or "").lower() for term in wc_terms):
        return True
    return any(fn and fn in nq for fn in fixture_norms)


_STATUS_ORDER = {"live": 0, "upcoming": 1, "unknown": 2, "finished": 3}


def _order_cards(cards: list[MatchCard]) -> list[MatchCard]:
    live = [c for c in cards if c.status == "live"]
    upcoming = sorted(
        [c for c in cards if c.status == "upcoming"], key=lambda c: c.utc_date or ""
    )
    unknown = [c for c in cards if c.status == "unknown"]
    finished = sorted(
        [c for c in cards if c.status == "finished"],
        key=lambda c: c.utc_date or "",
        reverse=True,
    )[:FINISHED_CAP]
    return live + upcoming + unknown + finished
