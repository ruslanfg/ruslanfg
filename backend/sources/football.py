"""football-data.org (v4) client — schedule, live scores, results, lineups.

Free tier notes (surfaced to the user in the README + UI):
  * Covers the FIFA World Cup competition (code "WC") but is rate limited.
  * Does NOT expose a precise live "minute"; we derive an APPROXIMATE minute
    from kickoff time and clearly label it as approximate.
  * Lineups are best-effort and may be empty on the free plan.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

from ..http_client import HttpClient, SourceError

_LIVE = {"IN_PLAY", "PAUSED", "SUSPENDED"}
_FINISHED = {"FINISHED", "AWARDED"}
_UPCOMING = {"SCHEDULED", "TIMED"}


def _parse_iso(s: str | None) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _approx_minute(kickoff_iso: str | None, raw_status: str) -> Optional[int]:
    """Approximate elapsed match minute from kickoff. The free API does not give
    a real clock, so this is an estimate (labeled as such in the UI)."""
    ko = _parse_iso(kickoff_iso)
    if ko is None:
        return None
    elapsed = (datetime.now(timezone.utc) - ko).total_seconds() / 60.0
    if elapsed < 0:
        return None
    if raw_status == "PAUSED":  # half-time
        return 45
    # crude allowance for the 15-minute half-time break once past ~45'
    if elapsed > 45:
        elapsed -= 15
    return max(1, min(int(round(elapsed)), 95))


def _status_bucket(raw: str) -> str:
    if raw in _LIVE:
        return "live"
    if raw in _FINISHED:
        return "finished"
    if raw in _UPCOMING:
        return "upcoming"
    return "unknown"


def normalize_match(m: dict[str, Any]) -> dict[str, Any]:
    raw_status = m.get("status", "")
    score = m.get("score", {}) or {}
    full = score.get("fullTime", {}) or {}
    home_t = m.get("homeTeam", {}) or {}
    away_t = m.get("awayTeam", {}) or {}
    bucket = _status_bucket(raw_status)
    minute = _approx_minute(m.get("utcDate"), raw_status) if bucket == "live" else None
    return {
        "id": str(m.get("id")),
        "status": bucket,
        "raw_status": raw_status,
        "utc_date": m.get("utcDate"),
        "stage": m.get("stage"),
        "group": m.get("group"),
        "home_id": str(home_t.get("id")) if home_t.get("id") is not None else None,
        "home_name": home_t.get("name") or home_t.get("shortName") or "Home",
        "home_crest": home_t.get("crest"),
        "away_id": str(away_t.get("id")) if away_t.get("id") is not None else None,
        "away_name": away_t.get("name") or away_t.get("shortName") or "Away",
        "away_crest": away_t.get("crest"),
        "home_goals": full.get("home"),
        "away_goals": full.get("away"),
        "minute": minute,
        "minute_approx": True,
    }


class FootballSource:
    name = "football"
    label = "Football data (football-data.org)"

    def __init__(self, cfg, http: HttpClient):
        self.cfg = cfg.football
        self.http = http

    @property
    def configured(self) -> bool:
        return self.cfg.configured

    def _headers(self) -> dict[str, str]:
        return {"X-Auth-Token": self.cfg.api_key}

    async def fetch_matches(self) -> list[dict[str, Any]]:
        if not self.configured:
            raise SourceError("no FOOTBALL_DATA_API_KEY set")
        url = f"{self.cfg.base_url}/competitions/{self.cfg.competition}/matches"
        data = await self.http.get_json(url, headers=self._headers())
        matches = data.get("matches") if isinstance(data, dict) else None
        if not isinstance(matches, list):
            raise SourceError("unexpected response shape")
        return [normalize_match(m) for m in matches]

    async def fetch_lineups(self, match_id: str) -> Optional[dict[str, Any]]:
        """Best-effort starting lineups for one match. Returns None if the plan
        does not include them or the call fails (caller degrades gracefully)."""
        if not self.configured:
            return None
        url = f"{self.cfg.base_url}/matches/{match_id}"
        try:
            data = await self.http.get_json(url, headers=self._headers())
        except SourceError:
            return None
        home = (data.get("homeTeam") or {}) if isinstance(data, dict) else {}
        away = (data.get("awayTeam") or {}) if isinstance(data, dict) else {}

        def _xi(team: dict) -> list[str]:
            lineup = team.get("lineup") or []
            names = [p.get("name") for p in lineup if isinstance(p, dict) and p.get("name")]
            return names[:11]

        home_xi, away_xi = _xi(home), _xi(away)
        if not home_xi and not away_xi:
            return None
        return {
            "home": home_xi,
            "away": away_xi,
            "formation_home": home.get("formation"),
            "formation_away": away.get("formation"),
        }


def team_goal_stats(team_id: str, finished: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Goals scored/conceded per game for a team, from ALL its finished matches.
    Used to make each match's expected total goals matchup-specific (not a
    constant). Returns {gf, ga, gpg, games} or None if no data."""
    games = [
        m
        for m in finished
        if (m.get("home_id") == team_id or m.get("away_id") == team_id)
        and m.get("home_goals") is not None
        and m.get("away_goals") is not None
    ]
    if not games:
        return None
    gf = ga = 0
    for m in games:
        is_home = m.get("home_id") == team_id
        gf += m["home_goals"] if is_home else m["away_goals"]
        ga += m["away_goals"] if is_home else m["home_goals"]
    n = len(games)
    return {"gf": gf / n, "ga": ga / n, "gpg": (gf + ga) / n, "games": n}


def recent_form(team_id: str, finished: list[dict[str, Any]], n: int = 5) -> Optional[dict[str, Any]]:
    """Compute a team's recent form from finished matches (most-recent `n`).
    Returns {"results": ["W","D","L",...], "ppg": float, "n": int} or None."""
    games = [
        m
        for m in finished
        if (m.get("home_id") == team_id or m.get("away_id") == team_id)
        and m.get("home_goals") is not None
        and m.get("away_goals") is not None
    ]
    games.sort(key=lambda m: m.get("utc_date") or "")
    games = games[-n:]
    if not games:
        return None
    results: list[str] = []
    points = 0
    for m in games:
        is_home = m.get("home_id") == team_id
        gf = m["home_goals"] if is_home else m["away_goals"]
        ga = m["away_goals"] if is_home else m["home_goals"]
        if gf > ga:
            results.append("W")
            points += 3
        elif gf == ga:
            results.append("D")
            points += 1
        else:
            results.append("L")
    return {"results": results, "ppg": round(points / len(games), 3), "n": len(games)}
