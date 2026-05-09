"""Generate attribution reports for a completed strategy run."""

from __future__ import annotations

import argparse
import sqlite3

import pandas as pd

from src.config import load_config
from src.reporting.attribution_report import build_attribution, write_attribution_report
from src.storage.parquet_store import ParquetMarketStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze strategy performance versus buy-and-hold.")
    parser.add_argument("--config", default="config/config.example.yaml", help="Path to YAML config.")
    parser.add_argument("--run-id", type=int, default=None, help="Strategy run id. Defaults to latest run.")
    args = parser.parse_args()

    cfg = load_config(args.config)
    run_id = args.run_id or _latest_run_id(cfg.state_db)
    if run_id is None:
        raise RuntimeError("No strategy run found. Run a backtest first.")

    universe = pd.DataFrame(_rows(cfg.state_db, "SELECT symbol, name, avg_amount_20d, volatility_20d, rank FROM universe_snapshots WHERE run_id = ? ORDER BY rank", (run_id,)))
    if universe.empty:
        raise RuntimeError(f"No universe rows found for run_id={run_id}.")

    market_store = ParquetMarketStore(cfg.parquet_dir)
    bars = market_store.read_bars(
        symbols=universe["symbol"].tolist(),
        interval=cfg.raw["data"]["bar_interval"],
        start_date=cfg.raw["data"]["start_date"],
        end_date=cfg.raw["data"]["end_date"],
    )

    equity_rows = _rows(
        cfg.state_db,
        """
        SELECT date, cash, market_value, total_equity, total_return, max_drawdown, trade_count
        FROM account_snapshots
        WHERE run_id = ?
        ORDER BY date
        """,
        (run_id,),
    )
    trades = _rows(
        cfg.state_db,
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
    signals = _rows(
        cfg.state_db,
        """
        SELECT signal_id, datetime, symbol, name, side, price, quantity,
               strategy, reason, status, reject_reason, audit_json
        FROM signals
        WHERE run_id = ?
        ORDER BY datetime, id
        """,
        (run_id,),
    )

    attribution = build_attribution(
        config=cfg.raw,
        initial_cash=cfg.initial_cash,
        bars=bars,
        universe=universe,
        equity_rows=equity_rows,
        trades=trades,
        signals=signals,
    )
    files = write_attribution_report(cfg.reporting_dir, attribution)

    summary = attribution["summary"]
    print(f"run_id: {run_id}")
    print(f"strategy_total_return: {summary['strategy_total_return']}")
    print(f"benchmark_total_return: {summary['benchmark_total_return']}")
    print(f"equity_gap_vs_70pct_buy_hold: {summary['equity_gap_vs_70pct_buy_hold']}")
    print(f"strategy_avg_exposure: {summary['strategy_avg_exposure']}")
    print(f"sell_end_missed_upside: {summary['sell_end_missed_upside']}")
    for name, path in files.items():
        print(f"{name}: {path}")


def _latest_run_id(db_path: str) -> int | None:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT MAX(id) FROM strategy_runs").fetchone()
        return None if row is None or row[0] is None else int(row[0])


def _rows(db_path: str, sql: str, params: tuple = ()) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


if __name__ == "__main__":
    main()
