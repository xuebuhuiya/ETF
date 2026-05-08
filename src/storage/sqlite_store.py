"""SQLite state store for simulated trading."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable


SCHEMA = """
CREATE TABLE IF NOT EXISTS strategy_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    initial_cash REAL NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER,
    run_id INTEGER NOT NULL,
    datetime TEXT NOT NULL,
    symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    side TEXT NOT NULL,
    price REAL NOT NULL,
    quantity INTEGER NOT NULL,
    strategy TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL,
    reject_reason TEXT,
    audit_json TEXT,
    FOREIGN KEY (run_id) REFERENCES strategy_runs(id)
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER,
    run_id INTEGER NOT NULL,
    datetime TEXT NOT NULL,
    signal_datetime TEXT,
    symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    side TEXT NOT NULL,
    signal_price REAL,
    price REAL NOT NULL,
    quantity INTEGER NOT NULL,
    amount REAL NOT NULL,
    fee REAL NOT NULL,
    slippage REAL NOT NULL,
    cash_after REAL NOT NULL,
    position_after INTEGER NOT NULL,
    reason TEXT NOT NULL,
    audit_json TEXT,
    FOREIGN KEY (run_id) REFERENCES strategy_runs(id)
);

CREATE TABLE IF NOT EXISTS positions (
    run_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    base_quantity INTEGER NOT NULL,
    avg_cost REAL NOT NULL,
    last_price REAL NOT NULL,
    market_value REAL NOT NULL,
    pnl REAL NOT NULL,
    PRIMARY KEY (run_id, symbol),
    FOREIGN KEY (run_id) REFERENCES strategy_runs(id)
);

CREATE TABLE IF NOT EXISTS account_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    cash REAL NOT NULL,
    market_value REAL NOT NULL,
    total_equity REAL NOT NULL,
    total_return REAL NOT NULL,
    max_drawdown REAL NOT NULL,
    trade_count INTEGER NOT NULL,
    FOREIGN KEY (run_id) REFERENCES strategy_runs(id)
);

CREATE TABLE IF NOT EXISTS universe_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    avg_amount_20d REAL NOT NULL,
    volatility_20d REAL NOT NULL,
    rank INTEGER NOT NULL,
    FOREIGN KEY (run_id) REFERENCES strategy_runs(id)
);
"""


class SQLiteStore:
    """Small SQLite adapter for strategy runs and outputs."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            self._ensure_columns(conn)

    def create_run(self, started_at: str, strategy_name: str, initial_cash: float, notes: str = "") -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO strategy_runs (started_at, strategy_name, initial_cash, notes)
                VALUES (?, ?, ?, ?)
                """,
                (started_at, strategy_name, initial_cash, notes),
            )
            return int(cursor.lastrowid)

    def replace_run_outputs(
        self,
        run_id: int,
        signals: Iterable[dict],
        trades: Iterable[dict],
        positions: Iterable[dict],
        snapshots: Iterable[dict],
        universe: Iterable[dict],
    ) -> None:
        with self.connect() as conn:
            for table in ("signals", "trades", "positions", "account_snapshots", "universe_snapshots"):
                conn.execute(f"DELETE FROM {table} WHERE run_id = ?", (run_id,))

            self._insert_dicts(conn, "signals", signals)
            self._insert_dicts(conn, "trades", trades)
            self._insert_dicts(conn, "positions", positions)
            self._insert_dicts(conn, "account_snapshots", snapshots)
            self._insert_dicts(conn, "universe_snapshots", universe)

    @staticmethod
    def _insert_dicts(conn: sqlite3.Connection, table: str, rows: Iterable[dict]) -> None:
        rows = list(rows)
        if not rows:
            return
        keys = list(rows[0].keys())
        placeholders = ", ".join("?" for _ in keys)
        columns = ", ".join(keys)
        values = [tuple(row[key] for key in keys) for row in rows]
        conn.executemany(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", values)

    @staticmethod
    def _ensure_columns(conn: sqlite3.Connection) -> None:
        required = {
            "signals": {
                "signal_id": "INTEGER",
                "audit_json": "TEXT",
            },
            "trades": {
                "signal_id": "INTEGER",
                "signal_datetime": "TEXT",
                "signal_price": "REAL",
                "audit_json": "TEXT",
            },
        }
        for table, columns in required.items():
            existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            for name, column_type in columns.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}")
