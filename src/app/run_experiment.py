"""Run train/validation/test strategy experiments on cached market data."""

from __future__ import annotations

import argparse

import pandas as pd

from src.config import load_config
from src.experiment.runner import run_experiment, write_experiment_reports
from src.experiment.split import splits_from_config
from src.storage.parquet_store import ParquetMarketStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ETF train/validation/test experiment.")
    parser.add_argument("--config", default="config/config.example.yaml", help="Path to YAML config.")
    parser.add_argument("--output-dir", default=None, help="Output directory. Defaults to reporting.output_dir.")
    args = parser.parse_args()

    cfg = load_config(args.config)
    splits = splits_from_config(cfg.raw)
    if not splits:
        raise RuntimeError("No experiment splits configured.")

    market_store = ParquetMarketStore(cfg.parquet_dir)
    bars = market_store.read_bars(
        interval=cfg.raw["data"]["bar_interval"],
        start_date=min(split.start_date for split in splits),
        end_date=max(split.end_date for split in splits),
    )
    result = run_experiment(cfg.raw, cfg.initial_cash, bars, splits)
    output_dir = args.output_dir or cfg.reporting_dir
    paths = write_experiment_reports(output_dir, result)

    rows = pd.DataFrame(result["rows"])
    summary = pd.DataFrame(result["summary"])
    walk_forward = pd.DataFrame(result["walk_forward"])
    metrics = pd.DataFrame(result["metrics"])
    selected = result["selected_variant"]
    print(f"selected_variant: {selected}")
    if not summary.empty:
        print(summary.to_string(index=False))
    else:
        print(rows.to_string(index=False))
    if not walk_forward.empty:
        print("walk_forward:")
        print(walk_forward.to_string(index=False))
    if not metrics.empty:
        print("metrics:")
        print(metrics.to_string(index=False))
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
