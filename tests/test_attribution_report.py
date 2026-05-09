from __future__ import annotations

import pandas as pd

from src.reporting.attribution_report import build_attribution


def _config() -> dict:
    return {
        "broker_sim": {
            "lot_size": 100,
            "fee_rate": 0,
            "min_fee": 0,
            "slippage_pct": 0,
        },
        "risk": {
            "max_total_position_pct": 0.7,
        },
    }


def test_attribution_estimates_sell_and_rejected_buy_opportunities() -> None:
    bars = pd.DataFrame(
        [
            {"symbol": "510300", "name": "沪深300ETF", "datetime": "2024-01-01", "open": 10, "close": 10},
            {"symbol": "510300", "name": "沪深300ETF", "datetime": "2024-01-02", "open": 11, "close": 11},
            {"symbol": "510300", "name": "沪深300ETF", "datetime": "2024-01-03", "open": 12, "close": 12},
        ]
    )
    universe = pd.DataFrame([{"symbol": "510300", "name": "沪深300ETF", "rank": 1}])
    equity_rows = [
        {"date": "2024-01-01", "cash": 9000, "market_value": 1000, "total_equity": 10000, "total_return": 0, "trade_count": 1},
        {"date": "2024-01-02", "cash": 9500, "market_value": 550, "total_equity": 10050, "total_return": 0.005, "trade_count": 2},
        {"date": "2024-01-03", "cash": 9500, "market_value": 600, "total_equity": 10100, "total_return": 0.01, "trade_count": 2},
    ]
    trades = [
        {
            "datetime": "2024-01-01",
            "symbol": "510300",
            "name": "沪深300ETF",
            "side": "buy",
            "price": 10,
            "quantity": 100,
            "amount": 1000,
            "fee": 0,
            "slippage": 0,
        },
        {
            "datetime": "2024-01-02",
            "symbol": "510300",
            "name": "沪深300ETF",
            "side": "sell",
            "price": 11,
            "quantity": 50,
            "amount": 550,
            "fee": 0,
            "slippage": 0,
        },
    ]
    signals = [
        {
            "datetime": "2024-01-02",
            "symbol": "510300",
            "name": "沪深300ETF",
            "side": "buy",
            "price": 11,
            "quantity": 100,
            "status": "rejected",
            "reject_reason": "trend_filter",
            "audit_json": "{}",
        }
    ]

    attribution = build_attribution(
        config=_config(),
        initial_cash=10_000,
        bars=bars,
        universe=universe,
        equity_rows=equity_rows,
        trades=trades,
        signals=signals,
    )

    assert attribution["summary"]["sell_end_missed_upside"] == 50
    assert attribution["summary"]["rejected_buy_end_opportunity"] == 0
    assert attribution["by_symbol"][0]["hold_after_first_sell_diff"] == 0
