"""SQLite persistence layer.

Tables (as required by the spec): ``markets``, ``trades``, ``tracked_wallets``,
``paper_positions``, ``paper_fills`` — plus ``bankroll_history`` (equity curve),
``source_health`` (which data sources returned data vs failed) and ``bot_state``
(bankroll, realized PnL, on/off toggle).

All access goes through the :class:`Database` class. WAL mode + a write lock make
it safe to share one DB file between the bot loop process and the API process.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (
    condition_id     TEXT PRIMARY KEY,
    question         TEXT,
    slug             TEXT,
    up_token_id      TEXT,
    down_token_id    TEXT,
    neg_risk         INTEGER DEFAULT 0,
    start_time       INTEGER,
    end_time         INTEGER,
    active           INTEGER DEFAULT 1,
    closed           INTEGER DEFAULT 0,
    resolved_outcome TEXT,            -- 'UP' | 'DOWN' | NULL
    resolved_at      INTEGER,
    source           TEXT,
    raw_json         TEXT,
    created_at       INTEGER,
    updated_at       INTEGER
);

CREATE TABLE IF NOT EXISTS trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet      TEXT NOT NULL,
    condition_id TEXT,
    token_id    TEXT,
    outcome     TEXT,                 -- 'UP' | 'DOWN'
    side        TEXT,                 -- 'BUY' | 'SELL'
    price       REAL,
    size        REAL,                 -- shares
    usd         REAL,                 -- notional in USDC
    timestamp   INTEGER,
    tx_hash     TEXT,
    source      TEXT,                 -- 'data_api' | 'onchain' | 'sim'
    created_at  INTEGER,
    UNIQUE(wallet, token_id, tx_hash, timestamp, side, size)
);
CREATE INDEX IF NOT EXISTS idx_trades_wallet_ts ON trades(wallet, timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_condition ON trades(condition_id);

CREATE TABLE IF NOT EXISTS tracked_wallets (
    wallet         TEXT PRIMARY KEY,
    first_seen     INTEGER,
    last_seen      INTEGER,
    trades_count   INTEGER DEFAULT 0,
    wins           INTEGER DEFAULT 0,
    losses         INTEGER DEFAULT 0,
    win_rate       REAL DEFAULT 0,
    realized_pnl   REAL DEFAULT 0,
    volume         REAL DEFAULT 0,
    vw_pnl         REAL DEFAULT 0,    -- volume-weighted pnl component
    score          REAL DEFAULT 0,
    rank           INTEGER,
    lookback_days  INTEGER,
    updated_at     INTEGER
);
CREATE INDEX IF NOT EXISTS idx_wallets_score ON tracked_wallets(score DESC);

CREATE TABLE IF NOT EXISTS paper_positions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    condition_id    TEXT,
    market_question TEXT,
    source_wallet   TEXT,
    outcome         TEXT,             -- 'UP' | 'DOWN'
    token_id        TEXT,
    entry_price     REAL,
    shares          REAL,
    size_usd        REAL,
    status          TEXT DEFAULT 'OPEN',  -- 'OPEN' | 'CLOSED'
    opened_at       INTEGER,
    market_end_time INTEGER,
    resolved_outcome TEXT,
    exit_price      REAL,
    pnl             REAL,
    closed_at       INTEGER
);
CREATE INDEX IF NOT EXISTS idx_positions_status ON paper_positions(status);
CREATE INDEX IF NOT EXISTS idx_positions_condition ON paper_positions(condition_id);

CREATE TABLE IF NOT EXISTS paper_fills (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id  INTEGER,
    kind         TEXT,                -- 'ENTRY' | 'RESOLUTION'
    side         TEXT,
    price        REAL,
    shares       REAL,
    size_usd     REAL,
    slippage_bps REAL,
    timestamp    INTEGER,
    note         TEXT,
    FOREIGN KEY(position_id) REFERENCES paper_positions(id)
);
CREATE INDEX IF NOT EXISTS idx_fills_position ON paper_fills(position_id);

CREATE TABLE IF NOT EXISTS bankroll_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp      INTEGER,
    bankroll       REAL,              -- free cash
    open_exposure  REAL,              -- cost basis of open positions
    equity         REAL,              -- bankroll + open_exposure
    realized_pnl   REAL,
    open_positions INTEGER
);
CREATE INDEX IF NOT EXISTS idx_bankroll_ts ON bankroll_history(timestamp);

CREATE TABLE IF NOT EXISTS source_health (
    source        TEXT PRIMARY KEY,
    status        TEXT DEFAULT 'unknown',  -- 'ok' | 'error' | 'unknown'
    last_ok_at    INTEGER,
    last_error_at INTEGER,
    last_error    TEXT,
    ok_count      INTEGER DEFAULT 0,
    err_count     INTEGER DEFAULT 0,
    detail        TEXT,
    updated_at    INTEGER
);

CREATE TABLE IF NOT EXISTS bot_state (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def now() -> int:
    return int(time.time())


class Database:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._conn.execute("PRAGMA busy_timeout=5000;")
        self.init_schema()

    def init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --------------------------------------------------------------------- #
    # Generic helpers
    # --------------------------------------------------------------------- #
    @staticmethod
    def _bind(params: Any) -> Any:
        # Pass mappings through untouched (named placeholders); tuple-ify sequences.
        from collections.abc import Mapping
        return params if isinstance(params, Mapping) else tuple(params)

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, self._bind(params))
            self._conn.commit()
            return cur

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, self._bind(params)).fetchall())

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    # --------------------------------------------------------------------- #
    # bot_state (key/value)
    # --------------------------------------------------------------------- #
    def get_state(self, key: str, default: Any = None) -> Any:
        row = self.query_one("SELECT value FROM bot_state WHERE key=?", (key,))
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            return row["value"]

    def set_state(self, key: str, value: Any) -> None:
        self.execute(
            "INSERT INTO bot_state(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )

    # --------------------------------------------------------------------- #
    # source_health  (feeds the Step-1 review)
    # --------------------------------------------------------------------- #
    def record_source(
        self, source: str, ok: bool, error: str | None = None, detail: str | None = None
    ) -> None:
        ts = now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO source_health(source) VALUES(?) "
                "ON CONFLICT(source) DO NOTHING",
                (source,),
            )
            if ok:
                self._conn.execute(
                    "UPDATE source_health SET status='ok', last_ok_at=?, "
                    "ok_count=ok_count+1, detail=COALESCE(?, detail), updated_at=? "
                    "WHERE source=?",
                    (ts, detail, ts, source),
                )
            else:
                self._conn.execute(
                    "UPDATE source_health SET status='error', last_error_at=?, "
                    "last_error=?, err_count=err_count+1, updated_at=? WHERE source=?",
                    (ts, error, ts, source),
                )
            self._conn.commit()

    def source_health(self) -> list[sqlite3.Row]:
        return self.query("SELECT * FROM source_health ORDER BY source")

    # --------------------------------------------------------------------- #
    # markets
    # --------------------------------------------------------------------- #
    def upsert_market(self, m: dict[str, Any]) -> None:
        ts = now()
        existing = self.query_one(
            "SELECT created_at FROM markets WHERE condition_id=?", (m["condition_id"],)
        )
        created = existing["created_at"] if existing else ts
        self.execute(
            """
            INSERT INTO markets(condition_id, question, slug, up_token_id, down_token_id,
                neg_risk, start_time, end_time, active, closed, resolved_outcome,
                resolved_at, source, raw_json, created_at, updated_at)
            VALUES(:condition_id, :question, :slug, :up_token_id, :down_token_id,
                :neg_risk, :start_time, :end_time, :active, :closed, :resolved_outcome,
                :resolved_at, :source, :raw_json, :created_at, :updated_at)
            ON CONFLICT(condition_id) DO UPDATE SET
                question=excluded.question, slug=excluded.slug,
                up_token_id=excluded.up_token_id, down_token_id=excluded.down_token_id,
                neg_risk=excluded.neg_risk, start_time=excluded.start_time,
                end_time=excluded.end_time, active=excluded.active, closed=excluded.closed,
                resolved_outcome=COALESCE(excluded.resolved_outcome, markets.resolved_outcome),
                resolved_at=COALESCE(excluded.resolved_at, markets.resolved_at),
                source=excluded.source, raw_json=excluded.raw_json,
                updated_at=excluded.updated_at
            """,
            {
                "condition_id": m["condition_id"],
                "question": m.get("question"),
                "slug": m.get("slug"),
                "up_token_id": m.get("up_token_id"),
                "down_token_id": m.get("down_token_id"),
                "neg_risk": int(m.get("neg_risk", 0)),
                "start_time": m.get("start_time"),
                "end_time": m.get("end_time"),
                "active": int(m.get("active", 1)),
                "closed": int(m.get("closed", 0)),
                "resolved_outcome": m.get("resolved_outcome"),
                "resolved_at": m.get("resolved_at"),
                "source": m.get("source"),
                "raw_json": json.dumps(m.get("raw")) if m.get("raw") is not None else None,
                "created_at": created,
                "updated_at": ts,
            },
        )

    def bulk_upsert_markets(self, markets: list[dict[str, Any]]) -> None:
        """Fast path for seeding many markets in one transaction."""
        ts = now()
        rows = [{
            "condition_id": m["condition_id"], "question": m.get("question"),
            "slug": m.get("slug"), "up_token_id": m.get("up_token_id"),
            "down_token_id": m.get("down_token_id"), "neg_risk": int(m.get("neg_risk", 0)),
            "start_time": m.get("start_time"), "end_time": m.get("end_time"),
            "active": int(m.get("active", 1)), "closed": int(m.get("closed", 0)),
            "resolved_outcome": m.get("resolved_outcome"), "resolved_at": m.get("resolved_at"),
            "source": m.get("source"),
            "raw_json": json.dumps(m.get("raw")) if m.get("raw") is not None else None,
            "created_at": ts, "updated_at": ts,
        } for m in markets]
        sql = (
            "INSERT INTO markets(condition_id, question, slug, up_token_id, down_token_id, "
            "neg_risk, start_time, end_time, active, closed, resolved_outcome, resolved_at, "
            "source, raw_json, created_at, updated_at) VALUES(:condition_id,:question,:slug,"
            ":up_token_id,:down_token_id,:neg_risk,:start_time,:end_time,:active,:closed,"
            ":resolved_outcome,:resolved_at,:source,:raw_json,:created_at,:updated_at) "
            "ON CONFLICT(condition_id) DO UPDATE SET "
            "resolved_outcome=COALESCE(excluded.resolved_outcome, markets.resolved_outcome), "
            "closed=excluded.closed, active=excluded.active, updated_at=excluded.updated_at"
        )
        with self._lock:
            self._conn.executemany(sql, rows)
            self._conn.commit()

    def bulk_insert_trades(self, trades: list[dict[str, Any]]) -> int:
        ts = now()
        rows = [(
            t["wallet"], t.get("condition_id"), t.get("token_id"), t.get("outcome"),
            t.get("side"), t.get("price"), t.get("size"), t.get("usd"),
            t.get("timestamp"), t.get("tx_hash"), t.get("source"), ts,
        ) for t in trades]
        with self._lock:
            cur = self._conn.executemany(
                "INSERT OR IGNORE INTO trades(wallet, condition_id, token_id, outcome, side, "
                "price, size, usd, timestamp, tx_hash, source, created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            self._conn.commit()
            return cur.rowcount

    def get_market(self, condition_id: str) -> sqlite3.Row | None:
        return self.query_one("SELECT * FROM markets WHERE condition_id=?", (condition_id,))

    def latest_market(self) -> sqlite3.Row | None:
        return self.query_one("SELECT * FROM markets ORDER BY end_time DESC LIMIT 1")

    # --------------------------------------------------------------------- #
    # trades (observed real trades from tracked wallets)
    # --------------------------------------------------------------------- #
    def insert_trade(self, t: dict[str, Any]) -> bool:
        """Insert a trade; returns True if newly inserted (False if duplicate)."""
        try:
            cur = self.execute(
                """
                INSERT INTO trades(wallet, condition_id, token_id, outcome, side,
                    price, size, usd, timestamp, tx_hash, source, created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    t["wallet"], t.get("condition_id"), t.get("token_id"),
                    t.get("outcome"), t.get("side"), t.get("price"), t.get("size"),
                    t.get("usd"), t.get("timestamp"), t.get("tx_hash"),
                    t.get("source"), now(),
                ),
            )
            return cur.rowcount > 0
        except sqlite3.IntegrityError:
            return False

    def wallet_trades(self, wallet: str, since: int | None = None) -> list[sqlite3.Row]:
        if since is None:
            return self.query(
                "SELECT * FROM trades WHERE wallet=? ORDER BY timestamp", (wallet,)
            )
        return self.query(
            "SELECT * FROM trades WHERE wallet=? AND timestamp>=? ORDER BY timestamp",
            (wallet, since),
        )

    def recent_trades(self, since: int) -> list[sqlite3.Row]:
        return self.query(
            "SELECT * FROM trades WHERE timestamp>=? ORDER BY timestamp", (since,)
        )

    def distinct_wallets(self, since: int) -> list[str]:
        rows = self.query(
            "SELECT DISTINCT wallet FROM trades WHERE timestamp>=?", (since,)
        )
        return [r["wallet"] for r in rows]

    # --------------------------------------------------------------------- #
    # tracked_wallets
    # --------------------------------------------------------------------- #
    def upsert_wallet(self, w: dict[str, Any]) -> None:
        self.execute(
            """
            INSERT INTO tracked_wallets(wallet, first_seen, last_seen, trades_count,
                wins, losses, win_rate, realized_pnl, volume, vw_pnl, score, rank,
                lookback_days, updated_at)
            VALUES(:wallet,:first_seen,:last_seen,:trades_count,:wins,:losses,
                :win_rate,:realized_pnl,:volume,:vw_pnl,:score,:rank,:lookback_days,:updated_at)
            ON CONFLICT(wallet) DO UPDATE SET
                last_seen=excluded.last_seen, trades_count=excluded.trades_count,
                wins=excluded.wins, losses=excluded.losses, win_rate=excluded.win_rate,
                realized_pnl=excluded.realized_pnl, volume=excluded.volume,
                vw_pnl=excluded.vw_pnl, score=excluded.score, rank=excluded.rank,
                lookback_days=excluded.lookback_days, updated_at=excluded.updated_at
            """,
            {
                "wallet": w["wallet"],
                "first_seen": w.get("first_seen", now()),
                "last_seen": w.get("last_seen", now()),
                "trades_count": w.get("trades_count", 0),
                "wins": w.get("wins", 0),
                "losses": w.get("losses", 0),
                "win_rate": w.get("win_rate", 0.0),
                "realized_pnl": w.get("realized_pnl", 0.0),
                "volume": w.get("volume", 0.0),
                "vw_pnl": w.get("vw_pnl", 0.0),
                "score": w.get("score", 0.0),
                "rank": w.get("rank"),
                "lookback_days": w.get("lookback_days"),
                "updated_at": now(),
            },
        )

    def top_wallets(self, n: int, min_trades: int = 0) -> list[sqlite3.Row]:
        return self.query(
            "SELECT * FROM tracked_wallets WHERE trades_count>=? "
            "ORDER BY score DESC, realized_pnl DESC LIMIT ?",
            (min_trades, n),
        )

    def all_wallets(self) -> list[sqlite3.Row]:
        return self.query("SELECT * FROM tracked_wallets ORDER BY score DESC")

    # --------------------------------------------------------------------- #
    # paper positions & fills
    # --------------------------------------------------------------------- #
    def open_position(self, p: dict[str, Any]) -> int:
        cur = self.execute(
            """
            INSERT INTO paper_positions(condition_id, market_question, source_wallet,
                outcome, token_id, entry_price, shares, size_usd, status, opened_at,
                market_end_time)
            VALUES(?,?,?,?,?,?,?,?, 'OPEN', ?, ?)
            """,
            (
                p["condition_id"], p.get("market_question"), p.get("source_wallet"),
                p["outcome"], p.get("token_id"), p["entry_price"], p["shares"],
                p["size_usd"], p.get("opened_at", now()), p.get("market_end_time"),
            ),
        )
        return int(cur.lastrowid)

    def add_fill(self, f: dict[str, Any]) -> None:
        self.execute(
            """
            INSERT INTO paper_fills(position_id, kind, side, price, shares, size_usd,
                slippage_bps, timestamp, note)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                f["position_id"], f["kind"], f.get("side"), f.get("price"),
                f.get("shares"), f.get("size_usd"), f.get("slippage_bps"),
                f.get("timestamp", now()), f.get("note"),
            ),
        )

    def close_position(
        self, position_id: int, resolved_outcome: str, exit_price: float, pnl: float
    ) -> None:
        self.execute(
            "UPDATE paper_positions SET status='CLOSED', resolved_outcome=?, "
            "exit_price=?, pnl=?, closed_at=? WHERE id=?",
            (resolved_outcome, exit_price, pnl, now(), position_id),
        )

    def open_positions(self) -> list[sqlite3.Row]:
        return self.query(
            "SELECT * FROM paper_positions WHERE status='OPEN' ORDER BY opened_at DESC"
        )

    def open_positions_for(self, condition_id: str) -> list[sqlite3.Row]:
        return self.query(
            "SELECT * FROM paper_positions WHERE status='OPEN' AND condition_id=?",
            (condition_id,),
        )

    def closed_positions(self, limit: int = 200) -> list[sqlite3.Row]:
        return self.query(
            "SELECT * FROM paper_positions WHERE status='CLOSED' "
            "ORDER BY closed_at DESC LIMIT ?",
            (limit,),
        )

    def position_exists(self, condition_id: str, source_wallet: str, outcome: str) -> bool:
        row = self.query_one(
            "SELECT 1 FROM paper_positions WHERE condition_id=? AND source_wallet=? "
            "AND outcome=?",
            (condition_id, source_wallet, outcome),
        )
        return row is not None

    def fills_for(self, position_id: int) -> list[sqlite3.Row]:
        return self.query(
            "SELECT * FROM paper_fills WHERE position_id=? ORDER BY timestamp", (position_id,)
        )

    # --------------------------------------------------------------------- #
    # bankroll / equity curve
    # --------------------------------------------------------------------- #
    def record_equity(
        self,
        bankroll: float,
        open_exposure: float,
        realized_pnl: float,
        open_positions: int,
    ) -> None:
        self.execute(
            "INSERT INTO bankroll_history(timestamp, bankroll, open_exposure, equity, "
            "realized_pnl, open_positions) VALUES(?,?,?,?,?,?)",
            (now(), bankroll, open_exposure, bankroll + open_exposure, realized_pnl,
             open_positions),
        )

    def equity_curve(self, limit: int = 1000) -> list[sqlite3.Row]:
        rows = self.query(
            "SELECT * FROM bankroll_history ORDER BY id DESC LIMIT ?", (limit,)
        )
        return list(reversed(rows))


__all__ = ["Database", "now"]
