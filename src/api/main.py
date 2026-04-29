"""FastAPI read-only dashboard API."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from src.config import load_config
from src.storage.parquet_store import ParquetMarketStore


cfg = load_config()
app = FastAPI(title="ETF Simulation API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.raw["api"]["cors_origins"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(cfg.state_db)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(sql: str, params: tuple = ()) -> list[dict]:
    with _connect() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _latest_run_id() -> int | None:
    with _connect() as conn:
        row = conn.execute("SELECT MAX(id) AS run_id FROM strategy_runs").fetchone()
        return None if row is None or row["run_id"] is None else int(row["run_id"])


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "state_db": str(cfg.state_db),
        "parquet_dir": str(cfg.parquet_dir),
        "has_state_db": Path(cfg.state_db).exists(),
    }


@app.get("/api/universe")
def universe(run_id: int | None = None) -> list[dict]:
    run_id = run_id or _latest_run_id()
    if run_id is None:
        return []
    return _rows(
        """
        SELECT symbol, name, avg_amount_20d, volatility_20d, rank
        FROM universe_snapshots
        WHERE run_id = ?
        ORDER BY rank
        """,
        (run_id,),
    )


@app.get("/api/bars")
def bars(
    symbol: str = Query(...),
    interval: str = "1d",
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    store = ParquetMarketStore(cfg.parquet_dir)
    frame = store.read_bars(
        symbols=[symbol],
        interval=interval,
        start_date=start_date,
        end_date=end_date,
    )
    return frame.to_dict(orient="records")


@app.get("/api/signals")
def signals(symbol: str | None = None, run_id: int | None = None) -> list[dict]:
    run_id = run_id or _latest_run_id()
    if run_id is None:
        return []
    if symbol:
        return _rows(
            """
            SELECT datetime, symbol, name, side, price, quantity, strategy, reason, status, reject_reason
            FROM signals
            WHERE run_id = ? AND symbol = ?
            ORDER BY datetime, id
            """,
            (run_id, symbol),
        )
    return _rows(
        """
        SELECT datetime, symbol, name, side, price, quantity, strategy, reason, status, reject_reason
        FROM signals
        WHERE run_id = ?
        ORDER BY datetime, id
        """,
        (run_id,),
    )


@app.get("/api/trades")
def trades(symbol: str | None = None, run_id: int | None = None) -> list[dict]:
    run_id = run_id or _latest_run_id()
    if run_id is None:
        return []
    if symbol:
        return _rows(
            """
            SELECT datetime, symbol, name, side, price, quantity, amount, fee, slippage, cash_after, position_after, reason
            FROM trades
            WHERE run_id = ? AND symbol = ?
            ORDER BY datetime, id
            """,
            (run_id, symbol),
        )
    return _rows(
        """
        SELECT datetime, symbol, name, side, price, quantity, amount, fee, slippage, cash_after, position_after, reason
        FROM trades
        WHERE run_id = ?
        ORDER BY datetime, id
        """,
        (run_id,),
    )


@app.get("/api/positions")
def positions(run_id: int | None = None) -> list[dict]:
    run_id = run_id or _latest_run_id()
    if run_id is None:
        return []
    return _rows(
        """
        SELECT symbol, name, quantity, base_quantity, avg_cost, last_price, market_value, pnl
        FROM positions
        WHERE run_id = ?
        ORDER BY symbol
        """,
        (run_id,),
    )


@app.get("/api/account/equity")
def equity(run_id: int | None = None) -> list[dict]:
    run_id = run_id or _latest_run_id()
    if run_id is None:
        return []
    return _rows(
        """
        SELECT date, cash, market_value, total_equity, total_return, max_drawdown, trade_count
        FROM account_snapshots
        WHERE run_id = ?
        ORDER BY date
        """,
        (run_id,),
    )
