from __future__ import annotations

import json

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


def test_rejected_buy_summary_uses_deduped_conservative_estimate() -> None:
    bars = pd.DataFrame(
        [
            {"symbol": "510300", "name": "沪深300ETF", "datetime": "2024-01-01", "open": 10, "close": 10},
            {"symbol": "510300", "name": "沪深300ETF", "datetime": "2024-01-02", "open": 11, "close": 11},
            {"symbol": "510300", "name": "沪深300ETF", "datetime": "2024-01-03", "open": 12, "close": 12},
            {"symbol": "510300", "name": "沪深300ETF", "datetime": "2024-01-04", "open": 13, "close": 13},
        ]
    )
    audit = json.dumps(
        {
            "cash_before_signal": 10_000,
            "total_equity_before_signal": 10_000,
            "total_market_value_before_signal": 0,
            "position_quantity_before_signal": 0,
            "last_price_before_signal": 10,
        },
        ensure_ascii=False,
    )
    signals = [
        {
            "datetime": "2024-01-01",
            "symbol": "510300",
            "name": "沪深300ETF",
            "side": "buy",
            "price": 10,
            "quantity": 100,
            "status": "rejected",
            "reject_reason": "trend_filter",
            "audit_json": audit,
        },
        {
            "datetime": "2024-01-02",
            "symbol": "510300",
            "name": "沪深300ETF",
            "side": "buy",
            "price": 11,
            "quantity": 100,
            "status": "rejected",
            "reject_reason": "trend_filter",
            "audit_json": audit,
        },
    ]

    attribution = build_attribution(
        config=_config(),
        initial_cash=10_000,
        bars=bars,
        universe=pd.DataFrame([{"symbol": "510300", "name": "沪深300ETF", "rank": 1}]),
        equity_rows=[
            {"date": "2024-01-01", "cash": 10_000, "market_value": 0, "total_equity": 10_000, "total_return": 0, "trade_count": 0},
            {"date": "2024-01-04", "cash": 10_000, "market_value": 0, "total_equity": 10_000, "total_return": 0, "trade_count": 0},
        ],
        trades=[],
        signals=signals,
    )

    assert attribution["summary"]["rejected_buy_upper_bound_end_opportunity"] == 300
    assert attribution["summary"]["rejected_buy_feasible_upper_bound_end_opportunity"] == 300
    assert attribution["summary"]["rejected_buy_end_opportunity"] == 200
