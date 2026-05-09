"""Compare strategy parameter variants on cached local market data."""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path

import pandas as pd

from src.config import load_config
from src.storage.parquet_store import ParquetMarketStore
from src.strategy.grid_t import GridTBacktester
from src.universe.filter import select_universe


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare ETF strategy parameter variants.")
    parser.add_argument("--config", default="config/config.example.yaml", help="Path to YAML config.")
    parser.add_argument("--output", default="reports/strategy_comparison.csv", help="CSV output path.")
    args = parser.parse_args()

    cfg = load_config(args.config)
    market_store = ParquetMarketStore(cfg.parquet_dir)
    bars = market_store.read_bars(
        interval=cfg.raw["data"]["bar_interval"],
        start_date=cfg.raw["data"]["start_date"],
        end_date=cfg.raw["data"]["end_date"],
    )
    universe = select_universe(bars, cfg.raw["universe"])
    if universe.empty:
        raise RuntimeError("No ETF candidates selected. Run a backtest and check universe thresholds.")

    rows = [_run_variant(name, variant, cfg.initial_cash, bars, universe) for name, variant in _variants(cfg.raw)]
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig")

    print(pd.DataFrame(rows).to_string(index=False))
    print(f"comparison_csv: {output_path}")


def _variants(base_config: dict) -> list[tuple[str, dict]]:
    no_trend = deepcopy(base_config)
    no_trend["strategy"]["trend_filter"] = {"enabled": False}

    current = deepcopy(base_config)

    strict = deepcopy(base_config)
    strict["strategy"]["trend_filter"] = {
        "enabled": True,
        "ma_short": 20,
        "ma_long": 60,
        "block_buy_below_ma_long": True,
        "require_short_ma_below_long_ma": False,
        "require_ma_short_above_ma_long": False,
    }

    return [
        ("no_trend_filter", no_trend),
        ("confirmed_downtrend_filter", current),
        ("strict_below_ma_long_filter", strict),
    ]


def _run_variant(name: str, config: dict, initial_cash: float, bars: pd.DataFrame, universe: pd.DataFrame) -> dict:
    account = GridTBacktester(config, initial_cash).run(run_id=0, bars=bars, universe=universe)
    final_snapshot = account.snapshots[-1]
    rejected = [signal for signal in account.signals if signal["status"] == "rejected"]
    trend_rejected = [signal for signal in rejected if signal.get("reject_reason") == "trend_filter"]
    return {
        "variant": name,
        "final_equity": final_snapshot["total_equity"],
        "total_return": final_snapshot["total_return"],
        "max_drawdown": final_snapshot["max_drawdown"],
        "trades": len(account.trades),
        "signals": len(account.signals),
        "rejected": len(rejected),
        "trend_filter_rejected": len(trend_rejected),
    }


if __name__ == "__main__":
    main()
