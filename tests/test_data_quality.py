from __future__ import annotations

import pandas as pd

from src.analysis.data_quality import build_data_quality_rows, summarize_data_quality


def test_data_quality_flags_missing_and_duplicate_rows() -> None:
    bars = pd.DataFrame(
        [
            {
                "symbol": "510300",
                "name": "沪深300ETF",
                "datetime": "2024-01-01",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10,
                "volume": 100,
                "amount": 1000,
            },
            {
                "symbol": "510300",
                "name": "沪深300ETF",
                "datetime": "2024-01-01",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": None,
                "volume": 100,
                "amount": 1000,
            },
            {
                "symbol": "510500",
                "name": "中证500ETF",
                "datetime": "2024-01-01",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10,
                "volume": 100,
                "amount": 1000,
            },
        ]
    )

    rows = build_data_quality_rows(bars, selection_lookback_days=1)
    summary = summarize_data_quality(rows)
    row_510300 = next(row for row in rows if row["symbol"] == "510300")

    assert row_510300["missing_required_values"] == 1
    assert row_510300["duplicate_dates"] == 1
    assert row_510300["enough_for_universe"] is False
    assert summary["symbol_count"] == 2
    assert summary["eligible_symbol_count"] == 1
