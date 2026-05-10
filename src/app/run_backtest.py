"""Run a local ETF simulation backtest."""

from __future__ import annotations

import argparse
from datetime import datetime

from src.app.backtest_window import prepare_universe_and_bars
from src.config import load_config
from src.data.akshare_data import fetch_etf_daily_bars, parse_symbol_list
from src.data.sample_data import generate_sample_bars
from src.reporting.audit_report import write_audit_reports
from src.reporting.csv_report import write_reports
from src.storage.parquet_store import ParquetMarketStore
from src.storage.sqlite_store import SQLiteStore
from src.strategy.grid_t import GridTBacktester


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ETF T+0 local simulation.")
    parser.add_argument("--config", default="config/config.example.yaml", help="Path to YAML config.")
    parser.add_argument(
        "--provider",
        choices=["sample", "akshare", "local"],
        default=None,
        help="Data provider. Defaults to config data.provider unless --sample is used.",
    )
    parser.add_argument("--sample", action="store_true", help="Use deterministic sample ETF bars.")
    parser.add_argument("--periods", type=int, default=120, help="Business-day sample length.")
    parser.add_argument(
        "--symbols",
        default=None,
        help="Comma-separated ETF symbols, optionally symbol:name. Example: 510300,159915:创业板ETF",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    state_store = SQLiteStore(cfg.state_db)
    state_store.initialize()

    market_store = ParquetMarketStore(cfg.parquet_dir)
    provider = "sample" if args.sample else (args.provider or cfg.raw["data"]["provider"])
    if provider == "sample":
        sample_bars = generate_sample_bars(start=cfg.raw["data"]["start_date"], periods=args.periods)
        market_store.write_bars(sample_bars, interval=cfg.raw["data"]["bar_interval"])
    elif provider == "akshare":
        symbol_arg = args.symbols or ",".join(cfg.raw["data"].get("default_symbols", []))
        requests = parse_symbol_list(symbol_arg)
        akshare_bars = fetch_etf_daily_bars(
            requests,
            start_date=cfg.raw["data"]["start_date"],
            end_date=cfg.raw["data"]["end_date"],
            adjust=cfg.raw["data"].get("adjust", ""),
        )
        if akshare_bars.empty:
            raise RuntimeError("AkShare returned no ETF bars. Check symbols, dates, or network.")
        market_store.write_bars(akshare_bars, interval=cfg.raw["data"]["bar_interval"])
    elif provider != "local":
        raise RuntimeError(f"Unsupported provider: {provider}")

    bars = market_store.read_bars(
        interval=cfg.raw["data"]["bar_interval"],
        start_date=cfg.raw["data"]["start_date"],
        end_date=cfg.raw["data"]["end_date"],
    )
    universe, trading_bars, universe_as_of_date = prepare_universe_and_bars(bars, cfg.raw["universe"])
    if universe.empty:
        raise RuntimeError("No ETF candidates selected. Check data or universe thresholds.")
    if trading_bars.empty:
        raise RuntimeError("No trading bars remain after universe selection warmup.")

    started_at = datetime.now().isoformat(timespec="seconds")
    run_id = state_store.create_run(
        started_at=started_at,
        strategy_name=cfg.raw["strategy"]["name"],
        initial_cash=cfg.initial_cash,
        notes=f"{provider} data; universe_as_of={universe_as_of_date}",
    )

    backtester = GridTBacktester(cfg.raw, cfg.initial_cash)
    account = backtester.run(run_id=run_id, bars=trading_bars, universe=universe)

    universe_rows = [
        {
            "run_id": run_id,
            "date": universe_as_of_date,
            "symbol": row.symbol,
            "name": row.name,
            "avg_amount_20d": round(float(row.avg_amount_20d), 2),
            "volatility_20d": round(float(row.volatility_20d), 6),
            "rank": int(row.rank),
        }
        for row in universe.itertuples(index=False)
    ]
    position_rows = account.position_rows(run_id)

    state_store.replace_run_outputs(
        run_id=run_id,
        signals=account.signals,
        trades=account.trades,
        positions=position_rows,
        snapshots=account.snapshots,
        universe=universe_rows,
    )
    files = write_reports(
        cfg.reporting_dir,
        signals=account.signals,
        trades=account.trades,
        positions=position_rows,
        snapshots=account.snapshots,
        universe=universe_rows,
    )
    files.update(write_audit_reports(cfg.reporting_dir, account.signals, account.trades))

    final_snapshot = account.snapshots[-1]
    print(f"run_id: {run_id}")
    print(f"bars: {len(bars)}")
    print(f"trading_bars: {len(trading_bars)}")
    print(f"universe_as_of: {universe_as_of_date}")
    print(f"universe: {len(universe)}")
    print(f"signals: {len(account.signals)}")
    print(f"trades: {len(account.trades)}")
    print(f"final_equity: {final_snapshot['total_equity']}")
    print(f"total_return: {final_snapshot['total_return']}")
    for name, path in files.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
