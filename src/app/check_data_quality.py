"""Check cached ETF bar data quality."""

from __future__ import annotations

import argparse

import pandas as pd

from src.analysis.data_quality import build_data_quality_rows, summarize_data_quality, write_data_quality_report
from src.config import load_config
from src.storage.parquet_store import ParquetMarketStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Check local ETF bar data quality.")
    parser.add_argument("--config", default="config/config.example.yaml", help="Path to YAML config.")
    parser.add_argument("--output-dir", default=None, help="Output directory. Defaults to reporting.output_dir.")
    args = parser.parse_args()

    cfg = load_config(args.config)
    store = ParquetMarketStore(cfg.parquet_dir)
    bars = store.read_bars(
        interval=cfg.raw["data"]["bar_interval"],
        start_date=cfg.raw["data"]["start_date"],
        end_date=cfg.raw["data"]["end_date"],
    )
    rows = build_data_quality_rows(
        bars,
        selection_lookback_days=int(cfg.raw["universe"].get("selection_lookback_days", 20)),
    )
    output_dir = args.output_dir or cfg.reporting_dir
    paths = write_data_quality_report(output_dir, rows)
    summary = summarize_data_quality(rows)

    print(pd.DataFrame([summary]).to_string(index=False))
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
