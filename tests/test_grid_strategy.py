from __future__ import annotations

import pandas as pd

from src.strategy.grid_t import GridTBacktester


def _config(
    *,
    fill_mode: str = "next_bar_open",
    max_grid_levels: int = 5,
    buy_cooldown_days: int = 0,
    trend_filter: dict | None = None,
) -> dict:
    return {
        "strategy": {
            "grid_pct": 0.05,
            "take_profit_pct": 0.05,
            "max_grid_levels": max_grid_levels,
            "buy_cooldown_days": buy_cooldown_days,
            "base_position_pct": 0.2,
            "trade_amount": 10_000,
            "allow_buy": True,
            "allow_sell": True,
            "trend_filter": trend_filter or {"enabled": False},
        },
        "broker_sim": {
            "lot_size": 100,
            "fee_rate": 0,
            "min_fee": 0,
            "slippage_pct": 0,
            "fill_mode": fill_mode,
        },
        "risk": {
            "max_total_position_pct": 1.0,
            "max_symbol_position_pct": 1.0,
            "min_cash_pct": 0,
            "max_trades_per_symbol_per_day": 10,
            "max_trades_per_day": 10,
            "protect_base_position": True,
        },
    }


def _bars(closes: list[float], opens: list[float] | None = None) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-01", periods=len(closes))
    opens = opens or closes
    return pd.DataFrame(
        [
            {
                "symbol": "510300",
                "name": "沪深300ETF",
                "datetime": dt.strftime("%Y-%m-%d"),
                "open": open_price,
                "high": max(open_price, close),
                "low": min(open_price, close),
                "close": close,
                "volume": 1_000_000,
                "amount": close * 1_000_000,
            }
            for dt, open_price, close in zip(dates, opens, closes, strict=True)
        ]
    )


def _universe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "510300",
                "name": "沪深300ETF",
                "avg_amount_20d": 100_000_000,
                "volatility_20d": 0.02,
                "rank": 1,
            }
        ]
    )


def test_next_bar_open_uses_next_day_open_without_future_fill() -> None:
    account = GridTBacktester(_config(), initial_cash=100_000).run(
        run_id=1,
        bars=_bars(closes=[10, 10], opens=[10, 11]),
        universe=_universe(),
    )

    assert len(account.trades) == 1
    base_trade = account.trades[0]
    assert base_trade["signal_datetime"] == "2024-01-01"
    assert base_trade["datetime"] == "2024-01-02"
    assert base_trade["signal_price"] == 10
    assert base_trade["price"] == 11


def test_buy_cooldown_records_rejected_grid_buy() -> None:
    account = GridTBacktester(_config(buy_cooldown_days=2), initial_cash=100_000).run(
        run_id=1,
        bars=_bars(closes=[10, 9, 8.4], opens=[10, 9, 9]),
        universe=_universe(),
    )

    rejected = [signal for signal in account.signals if signal["status"] == "rejected"]
    assert [signal["reject_reason"] for signal in rejected] == ["buy_cooldown_days"]
    assert len(account.trades) == 2


def test_max_grid_levels_records_rejected_grid_buy() -> None:
    account = GridTBacktester(_config(max_grid_levels=1), initial_cash=100_000).run(
        run_id=1,
        bars=_bars(closes=[10, 9, 8], opens=[10, 9, 9]),
        universe=_universe(),
    )

    rejected = [signal for signal in account.signals if signal["status"] == "rejected"]
    assert [signal["reject_reason"] for signal in rejected] == ["max_grid_levels"]
    assert len(account.trades) == 2


def test_trend_filter_records_rejected_grid_buy() -> None:
    account = GridTBacktester(
        _config(
            trend_filter={
                "enabled": True,
                "ma_short": 2,
                "ma_long": 3,
                "block_buy_below_ma_long": True,
                "require_short_ma_below_long_ma": True,
                "require_ma_short_above_ma_long": False,
            }
        ),
        initial_cash=100_000,
    ).run(
        run_id=1,
        bars=_bars(closes=[10, 10, 9], opens=[10, 10, 10]),
        universe=_universe(),
    )

    rejected = [signal for signal in account.signals if signal["status"] == "rejected"]
    assert [signal["reject_reason"] for signal in rejected] == ["trend_filter"]
    assert '"trend_filter_reason": "downtrend_below_ma_long"' in rejected[0]["audit_json"]
    assert len(account.trades) == 1
