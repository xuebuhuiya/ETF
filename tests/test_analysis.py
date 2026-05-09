from __future__ import annotations

import pandas as pd

from src.analysis.benchmark import build_buy_hold_curve
from src.analysis.regime import build_market_regimes, summarize_by_regime


def _config() -> dict:
    return {
        "broker_sim": {
            "lot_size": 100,
            "fee_rate": 0,
            "min_fee": 0,
            "slippage_pct": 0,
        }
    }


def _bars(closes: list[float]) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-01", periods=len(closes))
    return pd.DataFrame(
        [
            {
                "symbol": "510300",
                "name": "沪深300ETF",
                "datetime": dt.strftime("%Y-%m-%d"),
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1_000_000,
                "amount": close * 1_000_000,
            }
            for dt, close in zip(dates, closes, strict=True)
        ]
    )


def _universe() -> pd.DataFrame:
    return pd.DataFrame([{"symbol": "510300", "name": "沪深300ETF", "rank": 1}])


def test_buy_hold_curve_uses_initial_buy_then_holds() -> None:
    curve = build_buy_hold_curve(
        name="buy_hold",
        config=_config(),
        initial_cash=10_000,
        bars=_bars([10, 12]),
        universe=_universe(),
        target_position_pct=1.0,
    )

    assert curve[-1]["total_equity"] == 12_000
    assert curve[-1]["total_return"] == 0.2
    assert curve[-1]["trade_count"] == 1


def test_market_regime_summary_compares_strategy_to_benchmark() -> None:
    bars = _bars([10, 11, 12, 11, 10, 9])
    regimes = build_market_regimes(
        bars,
        _universe(),
        short_window=2,
        long_window=3,
        momentum_window=1,
        up_momentum_pct=0.03,
        down_momentum_pct=-0.03,
    )
    assert any(row["regime"] == "uptrend" for row in regimes)
    assert any(row["regime"] == "downtrend" for row in regimes)

    equity_rows = [
        {"date": row["date"], "total_equity": 10_000 + index * 100}
        for index, row in enumerate(regimes)
    ]
    benchmark_rows = [
        {"date": row["date"], "total_equity": 10_000 + index * 50}
        for index, row in enumerate(regimes)
    ]
    summary = summarize_by_regime(
        equity_rows=equity_rows,
        benchmark_rows=benchmark_rows,
        trades=[{"datetime": regimes[-1]["date"]}],
        regime_rows=regimes,
    )

    assert {row["regime"] for row in summary} >= {"uptrend", "downtrend"}
    assert sum(row["trade_count"] for row in summary) == 1
