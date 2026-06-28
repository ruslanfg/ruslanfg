"""the-odds-api.com client — head-to-head (1X2) sportsbook odds.

Decimal odds are converted to implied probability (1/price) and then de-vigged
per bookmaker (normalized so home+draw+away sum to 1), then averaged across
books. We never invent a price: if the API is unavailable, the caller shows
"data unavailable".
"""
from __future__ import annotations

import unicodedata
from typing import Any, Optional

from ..http_client import HttpClient, SourceError

_STOPWORDS = {"fc", "national", "team", "the", "republic", "of"}


def normalize_team(name: str | None) -> str:
    if not name:
        return ""
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    n = n.lower()
    out = []
    for ch in n:
        out.append(ch if ch.isalnum() or ch == " " else " ")
    tokens = [t for t in "".join(out).split() if t and t not in _STOPWORDS]
    return " ".join(tokens)


def _devig(home: float, draw: float | None, away: float) -> tuple[float, Optional[float], float]:
    parts = [home] + ([draw] if draw is not None else []) + [away]
    s = sum(parts)
    if s <= 0:
        return home, draw, away
    if draw is None:
        return home / s, None, away / s
    return home / s, draw / s, away / s


class OddsSource:
    name = "odds"
    label = "Sportsbook odds (the-odds-api.com)"

    def __init__(self, cfg, http: HttpClient):
        self.cfg = cfg.odds
        self.http = http

    @property
    def configured(self) -> bool:
        return self.cfg.configured

    async def fetch_h2h(self) -> list[dict[str, Any]]:
        if not self.configured:
            raise SourceError("no THE_ODDS_API_KEY set")
        url = f"{self.cfg.base_url}/sports/{self.cfg.sport_key}/odds"
        params = {
            "apiKey": self.cfg.api_key,
            "regions": self.cfg.regions,
            "markets": "h2h",
            "oddsFormat": "decimal",
        }
        data = await self.http.get_json(url, params=params)
        if not isinstance(data, list):
            raise SourceError("unexpected response shape")
        return [e for e in (self._normalize_event(ev) for ev in data) if e]

    def _normalize_event(self, ev: dict[str, Any]) -> Optional[dict[str, Any]]:
        home_team = ev.get("home_team")
        away_team = ev.get("away_team")
        if not home_team or not away_team:
            return None
        h_sum = d_sum = a_sum = 0.0
        books = 0
        book_titles: list[str] = []
        for bk in ev.get("bookmakers", []) or []:
            market = next((m for m in bk.get("markets", []) if m.get("key") == "h2h"), None)
            if not market:
                continue
            ph = pd = pa = None
            for oc in market.get("outcomes", []) or []:
                price = oc.get("price")
                if not price or price <= 1.0:
                    continue
                name = oc.get("name", "")
                imp = 1.0 / price
                if name == "Draw":
                    pd = imp
                elif name == home_team:
                    ph = imp
                elif name == away_team:
                    pa = imp
            if ph is None or pa is None:
                continue
            ph, pd, pa = _devig(ph, pd, pa)
            h_sum += ph
            d_sum += pd or 0.0
            a_sum += pa
            books += 1
            if bk.get("title"):
                book_titles.append(bk["title"])
        if books == 0:
            return None
        return {
            "home_team": home_team,
            "away_team": away_team,
            "home_norm": normalize_team(home_team),
            "away_norm": normalize_team(away_team),
            "commence_time": ev.get("commence_time"),
            "home_pct": round(h_sum / books, 4),
            "draw_pct": round(d_sum / books, 4) if d_sum > 0 else None,
            "away_pct": round(a_sum / books, 4),
            "book_count": books,
            "books": book_titles[:6],
        }


def match_odds_to_fixture(
    home_name: str, away_name: str, odds_events: list[dict[str, Any]]
) -> Optional[dict[str, Any]]:
    """Find the odds event whose teams match this fixture (normalized names,
    either orientation). Returns the event with a `flipped` flag if the book
    lists the teams in the opposite home/away order."""
    hn, an = normalize_team(home_name), normalize_team(away_name)
    if not hn or not an:
        return None
    for ev in odds_events:
        if ev["home_norm"] == hn and ev["away_norm"] == an:
            return {**ev, "flipped": False}
        if ev["home_norm"] == an and ev["away_norm"] == hn:
            return {**ev, "flipped": True}
    # looser containment fallback (handles short vs long names)
    for ev in odds_events:
        if (hn in ev["home_norm"] or ev["home_norm"] in hn) and (
            an in ev["away_norm"] or ev["away_norm"] in an
        ):
            return {**ev, "flipped": False}
    return None
