"""SQLite persistence: a small key/value cache for raw API responses, the
computed Elo table, source-health status, and historical dashboard snapshots.

The API server reads the *latest* computed snapshot from here, so the dashboard
stays fast and resilient even while a refresh is in flight or a source is down.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key        TEXT PRIMARY KEY,
    fetched_at INTEGER NOT NULL,
    ok         INTEGER NOT NULL,
    payload    TEXT,
    error      TEXT
);

CREATE TABLE IF NOT EXISTS source_status (
    name       TEXT PRIMARY KEY,
    ok         INTEGER NOT NULL,
    detail     TEXT,
    last_ok_at INTEGER,
    checked_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS elo (
    team_id    TEXT PRIMARY KEY,
    team_name  TEXT,
    rating     REAL NOT NULL,
    matches    INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at INTEGER NOT NULL,
    payload    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_created ON snapshots (created_at);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: APScheduler jobs and request handlers may run
        # on different threads; we serialize via a short-lived connection per op.
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # -- raw response cache ---------------------------------------------------
    def put_cache(self, key: str, ok: bool, payload: Any = None, error: str | None = None) -> None:
        self._conn.execute(
            "INSERT INTO cache (key, fetched_at, ok, payload, error) VALUES (?,?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET fetched_at=excluded.fetched_at, ok=excluded.ok, "
            "payload=excluded.payload, error=excluded.error",
            (key, int(time.time()), 1 if ok else 0, json.dumps(payload) if ok else None, error),
        )
        self._conn.commit()

    def get_cache(self, key: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM cache WHERE key=?", (key,)).fetchone()
        if not row:
            return None
        return {
            "key": row["key"],
            "fetched_at": row["fetched_at"],
            "ok": bool(row["ok"]),
            "payload": json.loads(row["payload"]) if row["payload"] else None,
            "error": row["error"],
        }

    # -- source health --------------------------------------------------------
    def set_source_status(self, name: str, ok: bool, detail: str | None) -> None:
        now = int(time.time())
        prev = self._conn.execute(
            "SELECT last_ok_at FROM source_status WHERE name=?", (name,)
        ).fetchone()
        last_ok = now if ok else (prev["last_ok_at"] if prev else None)
        self._conn.execute(
            "INSERT INTO source_status (name, ok, detail, last_ok_at, checked_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET ok=excluded.ok, detail=excluded.detail, "
            "last_ok_at=excluded.last_ok_at, checked_at=excluded.checked_at",
            (name, 1 if ok else 0, detail, last_ok, now),
        )
        self._conn.commit()

    def get_source_statuses(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM source_status ORDER BY name").fetchall()
        return [
            {
                "name": r["name"],
                "ok": bool(r["ok"]),
                "detail": r["detail"],
                "last_ok_at": r["last_ok_at"],
                "checked_at": r["checked_at"],
            }
            for r in rows
        ]

    # -- Elo ------------------------------------------------------------------
    def upsert_elo(self, ratings: dict[str, dict[str, Any]]) -> None:
        now = int(time.time())
        with self._conn:
            self._conn.execute("DELETE FROM elo")
            self._conn.executemany(
                "INSERT INTO elo (team_id, team_name, rating, matches, updated_at) VALUES (?,?,?,?,?)",
                [
                    (tid, v["name"], v["rating"], v["matches"], now)
                    for tid, v in ratings.items()
                ],
            )

    def get_elo(self) -> dict[str, dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM elo").fetchall()
        return {
            r["team_id"]: {"name": r["team_name"], "rating": r["rating"], "matches": r["matches"]}
            for r in rows
        }

    # -- snapshots ------------------------------------------------------------
    def put_snapshot(self, payload: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT INTO snapshots (created_at, payload) VALUES (?,?)",
            (int(time.time()), json.dumps(payload)),
        )
        # keep the table bounded
        self._conn.execute(
            "DELETE FROM snapshots WHERE id NOT IN "
            "(SELECT id FROM snapshots ORDER BY created_at DESC LIMIT 500)"
        )
        self._conn.commit()

    def latest_snapshot(self) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT payload FROM snapshots ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        return json.loads(row["payload"]) if row else None

    def close(self) -> None:
        self._conn.close()
