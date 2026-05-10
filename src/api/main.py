"""FastAPI read-only dashboard API."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from src.analysis.benchmark import build_buy_hold_curve
from src.analysis.regime import build_market_regimes, summarize_by_regime
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


def _with_audit(rows: list[dict]) -> list[dict]:
    for row in rows:
        audit_json = row.pop("audit_json", None)
        if not audit_json:
            row["audit"] = {}
            continue
        try:
            row["audit"] = json.loads(audit_json)
        except json.JSONDecodeError:
            row["audit"] = {}
    return rows


def _latest_run_id() -> int | None:
    with _connect() as conn:
        row = conn.execute("SELECT MAX(id) AS run_id FROM strategy_runs").fetchone()
        return None if row is None or row["run_id"] is None else int(row["run_id"])


def _universe_rows(run_id: int) -> list[dict]:
    return _rows(
        """
        SELECT symbol, name, avg_amount_20d, volatility_20d, rank
        FROM universe_snapshots
        WHERE run_id = ?
        ORDER BY rank
        """,
        (run_id,),
    )


def _universe_frame(run_id: int) -> pd.DataFrame:
    return pd.DataFrame(_universe_rows(run_id))


def _bars_for_universe(universe_frame: pd.DataFrame, run_id: int | None = None) -> pd.DataFrame:
    if universe_frame.empty:
        return pd.DataFrame()
    start_date = cfg.raw["data"]["start_date"]
    if run_id is not None:
        rows = _rows("SELECT MIN(date) AS start_date FROM account_snapshots WHERE run_id = ?", (run_id,))
        if rows and rows[0].get("start_date"):
            start_date = str(rows[0]["start_date"])[:10]
    store = ParquetMarketStore(cfg.parquet_dir)
    return store.read_bars(
        symbols=universe_frame["symbol"].tolist(),
        interval=cfg.raw["data"]["bar_interval"],
        start_date=start_date,
        end_date=cfg.raw["data"]["end_date"],
    )


def _benchmark_entry_date(run_id: int) -> str | None:
    rows = _rows("SELECT MIN(datetime) AS entry_date FROM trades WHERE run_id = ? AND side = 'buy'", (run_id,))
    if rows and rows[0].get("entry_date"):
        return str(rows[0]["entry_date"])[:10]
    return None


def _report_csv(filename: str) -> list[dict]:
    path = Path(cfg.reporting_dir) / filename
    if not path.exists():
        return []
    frame = pd.read_csv(path)
    return frame.where(pd.notna(frame), None).to_dict(orient="records")


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
    return _universe_rows(run_id)


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
        rows = _rows(
            """
            SELECT signal_id, datetime, symbol, name, side, price, quantity,
                   strategy, reason, status, reject_reason, audit_json
            FROM signals
            WHERE run_id = ? AND symbol = ?
            ORDER BY datetime, id
            """,
            (run_id, symbol),
        )
        return _with_audit(rows)
    rows = _rows(
        """
        SELECT signal_id, datetime, symbol, name, side, price, quantity,
               strategy, reason, status, reject_reason, audit_json
        FROM signals
        WHERE run_id = ?
        ORDER BY datetime, id
        """,
        (run_id,),
    )
    return _with_audit(rows)


@app.get("/api/trades")
def trades(symbol: str | None = None, run_id: int | None = None) -> list[dict]:
    run_id = run_id or _latest_run_id()
    if run_id is None:
        return []
    if symbol:
        rows = _rows(
            """
            SELECT signal_id, datetime, signal_datetime, symbol, name, side,
                   signal_price, price, quantity, amount, fee, slippage,
                   cash_after, position_after, reason, audit_json
            FROM trades
            WHERE run_id = ? AND symbol = ?
            ORDER BY datetime, id
            """,
            (run_id, symbol),
        )
        return _with_audit(rows)
    rows = _rows(
        """
        SELECT signal_id, datetime, signal_datetime, symbol, name, side,
               signal_price, price, quantity, amount, fee, slippage,
               cash_after, position_after, reason, audit_json
        FROM trades
        WHERE run_id = ?
        ORDER BY datetime, id
        """,
        (run_id,),
    )
    return _with_audit(rows)


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


@app.get("/api/benchmarks/equity")
def benchmark_equity(run_id: int | None = None) -> list[dict]:
    run_id = run_id or _latest_run_id()
    if run_id is None:
        return []
    universe_frame = _universe_frame(run_id)
    bars_frame = _bars_for_universe(universe_frame, run_id)
    if universe_frame.empty or bars_frame.empty:
        return []

    fair_curve = build_buy_hold_curve(
        name="buy_hold_max_total_position",
        config=cfg.raw,
        initial_cash=cfg.initial_cash,
        bars=bars_frame,
        universe=universe_frame,
        target_position_pct=float(cfg.raw["risk"]["max_total_position_pct"]),
        entry_date=_benchmark_entry_date(run_id),
    )
    full_curve = build_buy_hold_curve(
        name="buy_hold_full_position",
        config=cfg.raw,
        initial_cash=cfg.initial_cash,
        bars=bars_frame,
        universe=universe_frame,
        target_position_pct=1.0,
        entry_date=_benchmark_entry_date(run_id),
    )
    return fair_curve + full_curve


@app.get("/api/regimes/summary")
def regime_summary(run_id: int | None = None) -> list[dict]:
    run_id = run_id or _latest_run_id()
    if run_id is None:
        return []
    universe_frame = _universe_frame(run_id)
    bars_frame = _bars_for_universe(universe_frame, run_id)
    if universe_frame.empty or bars_frame.empty:
        return []

    fair_curve = build_buy_hold_curve(
        name="buy_hold_max_total_position",
        config=cfg.raw,
        initial_cash=cfg.initial_cash,
        bars=bars_frame,
        universe=universe_frame,
        target_position_pct=float(cfg.raw["risk"]["max_total_position_pct"]),
        entry_date=_benchmark_entry_date(run_id),
    )
    regime_rows = build_market_regimes(bars_frame, universe_frame)
    return summarize_by_regime(
        equity_rows=equity(run_id),
        benchmark_rows=fair_curve,
        trades=trades(run_id=run_id),
        regime_rows=regime_rows,
    )


@app.get("/api/experiments/summary")
def experiment_summary() -> list[dict]:
    return _report_csv("experiment_summary.csv")


@app.get("/api/experiments/comparison")
def experiment_comparison() -> list[dict]:
    return _report_csv("experiment_comparison.csv")


@app.get("/api/experiments/walk-forward")
def experiment_walk_forward() -> list[dict]:
    return _report_csv("experiment_walk_forward.csv")
