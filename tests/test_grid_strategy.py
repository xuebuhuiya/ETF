from __future__ import annotations

import pandas as pd

from src.broker_sim.account import SimAccount
from src.strategy.grid_t import GridTBacktester


def _config(
    *,
    fill_mode: str = "next_bar_open",
    max_grid_levels: int = 5,
    buy_cooldown_days: int = 0,
    trend_filter: dict | None = None,
    extra_strategy: dict | None = None,
) -> dict:
    strategy = {
        "grid_pct": 0.05,
        "take_profit_pct": 0.05,
        "max_grid_levels": max_grid_levels,
        "buy_cooldown_days": buy_cooldown_days,
        "base_position_pct": 0.2,
        "trade_amount": 10_000,
        "allow_buy": True,
        "allow_sell": True,
        "trend_filter": trend_filter or {"enabled": False},
    }
    strategy.update(extra_strategy or {})
    return {
        "strategy": strategy,
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


def test_risk_checks_use_slippage_adjusted_fill_price() -> None:
    config = _config()
    config["broker_sim"]["slippage_pct"] = 0.1
    account = SimAccount(1_000, config["broker_sim"], config["risk"])
    pending = account.submit_signal(
        run_id=1,
        dt="2024-01-01",
        symbol="510300",
        name="沪深300ETF",
        side="buy",
        price=10,
        quantity=100,
        strategy="test",
        reason="test",
    )

    account.execute_pending_signal(pending, execution_dt="2024-01-02", execution_price=10)

    assert account.signals[0]["status"] == "rejected"
    assert account.signals[0]["reject_reason"] == "insufficient_cash"
    assert account.trades == []


def test_grid_sell_uses_grid_lot_entry_price_not_average_cost() -> None:
    account = GridTBacktester(_config(), initial_cash=100_000).run(
        run_id=1,
        bars=_bars(closes=[10, 9, 9.5, 9.5], opens=[10, 10, 9, 9.5]),
        universe=_universe(),
    )

    sells = [trade for trade in account.trades if trade["side"] == "sell"]
    assert len(sells) == 1
    assert sells[0]["signal_datetime"] == "2024-01-03"
    assert sells[0]["datetime"] == "2024-01-04"


def test_uptrend_slow_sell_raises_effective_take_profit() -> None:
    backtester = GridTBacktester(
        _config(
            extra_strategy={
                "slow_sell_in_uptrend": {
                    "enabled": True,
                    "take_profit_multiplier": 2,
                }
            }
        ),
        initial_cash=100_000,
    )

    params = backtester._effective_grid_params({"trend_up": True})

    assert params["take_profit_pct"] == 0.1
    assert params["uptrend_sell_multiplier"] == 2


def test_uptrend_slow_sell_consumes_lots_with_effective_take_profit() -> None:
    backtester = GridTBacktester(_config(), initial_cash=100_000)
    backtester.grid_lots["510300"] = [{"quantity": 100, "entry_price": 10.0}]
    backtester.grid_levels["510300"] = 1

    backtester._consume_grid_lots("510300", 100, 10.6, take_profit_pct=0.1)

    assert backtester.grid_lots["510300"] == [{"quantity": 100, "entry_price": 10.0}]
    assert backtester.grid_levels["510300"] == 1


def test_adaptive_grid_widens_grid_when_volatility_is_high() -> None:
    backtester = GridTBacktester(
        _config(
            extra_strategy={
                "adaptive_grid": {
                    "enabled": True,
                    "base_volatility": 0.01,
                    "min_multiplier": 0.75,
                    "max_multiplier": 2,
                }
            }
        ),
        initial_cash=100_000,
    )

    params = backtester._effective_grid_params({"trend_volatility": 0.02})

    assert params["grid_pct"] == 0.1
    assert params["take_profit_pct"] == 0.1
    assert params["volatility_multiplier"] == 2


def test_adaptive_grid_lot_consumption_matches_signal_take_profit() -> None:
    backtester = GridTBacktester(_config(), initial_cash=100_000)
    backtester.grid_lots["510300"] = [{"quantity": 100, "entry_price": 10.0}]
    backtester.grid_levels["510300"] = 1

    pending = {
        "audit": {"effective_take_profit_pct": 0.08},
        "quantity": 100,
        "signal_price": 10.7,
    }
    backtester._consume_grid_lots(
        "510300",
        int(pending["quantity"]),
        float(pending["signal_price"]),
        take_profit_pct=backtester._pending_take_profit_pct(pending),
    )

    assert backtester.grid_lots["510300"] == [{"quantity": 100, "entry_price": 10.0}]

    pending["signal_price"] = 10.8
    backtester._consume_grid_lots(
        "510300",
        int(pending["quantity"]),
        float(pending["signal_price"]),
        take_profit_pct=backtester._pending_take_profit_pct(pending),
    )

    assert backtester.grid_lots["510300"] == []


def test_trend_enhanced_base_adds_base_when_uptrend() -> None:
    account = GridTBacktester(
        _config(
            extra_strategy={
                "trend_enhanced_base": {
                    "enabled": True,
                    "ma_short": 2,
                    "ma_long": 3,
                    "uptrend_base_position_pct": 0.6,
                }
            }
        ),
        initial_cash=100_000,
    ).run(
        run_id=1,
        bars=_bars(closes=[10, 10, 11, 12, 13], opens=[10, 10, 11, 12, 13]),
        universe=_universe(),
    )

    assert any(signal["reason"] == "increase_base_position" for signal in account.signals)
    assert any("increase_base_position" in trade["reason"] for trade in account.trades)
