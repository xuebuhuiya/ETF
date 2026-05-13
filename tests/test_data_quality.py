from __future__ import annotations

import pandas as pd

from src.analysis.data_quality import build_data_quality_rows, summarize_data_quality


def _bar(symbol: str, name: str, dt: str, close: float = 10) -> dict:
    return {
        "symbol": symbol,
        "name": name,
        "datetime": dt,
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": 100,
        "amount": close * 100,
    }


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
    assert row_510300["actual_trading_days"] == 1
    assert row_510300["expected_trading_days"] == 1
    assert row_510300["enough_for_universe"] is False
    assert summary["symbol_count"] == 2
    assert summary["eligible_symbol_count"] == 1


def test_data_quality_uses_market_trading_dates_not_business_day_calendar() -> None:
    bars = pd.DataFrame(
        [
            _bar("510300", "沪深300ETF", "2024-01-02"),
            _bar("510300", "沪深300ETF", "2024-01-04"),
            _bar("510500", "中证500ETF", "2024-01-02"),
            _bar("510500", "中证500ETF", "2024-01-04"),
        ]
    )

    rows = build_data_quality_rows(bars, selection_lookback_days=1)

    assert {row["expected_trading_days"] for row in rows} == {2}
    assert all(row["actual_trading_days"] == 2 for row in rows)
    assert all(row["data_completeness"] == 1.0 for row in rows)


def test_data_quality_drops_when_symbol_misses_actual_market_day() -> None:
    bars = pd.DataFrame(
        [
            _bar("510300", "沪深300ETF", "2024-01-02"),
            _bar("510300", "沪深300ETF", "2024-01-03"),
            _bar("510300", "沪深300ETF", "2024-01-04"),
            _bar("510500", "中证500ETF", "2024-01-02"),
            _bar("510500", "中证500ETF", "2024-01-04"),
        ]
    )

    rows = build_data_quality_rows(bars, selection_lookback_days=1)
    row_510500 = next(row for row in rows if row["symbol"] == "510500")

    assert row_510500["expected_trading_days"] == 3
    assert row_510500["actual_trading_days"] == 2
    assert row_510500["data_completeness"] == 0.666667
