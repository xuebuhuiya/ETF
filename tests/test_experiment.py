from __future__ import annotations

import pandas as pd

from src.experiment.runner import run_experiment
from src.experiment.split import ExperimentSplit, slice_bars, splits_from_config, walk_forward_windows_from_config
from src.experiment.variants import strategy_variants


def _config() -> dict:
    return {
        "universe": {
            "selection_lookback_days": 20,
            "max_candidates": 10,
            "min_price": 0.5,
            "min_avg_amount_20d": 1,
            "min_volatility_20d": 0.001,
            "max_volatility_20d": 0.2,
        },
        "strategy": {
            "name": "grid_t",
            "grid_pct": 0.03,
            "take_profit_pct": 0.03,
            "max_grid_levels": 3,
            "buy_cooldown_days": 0,
            "base_position_pct": 0.3,
            "trade_amount": 2_000,
            "allow_buy": True,
            "allow_sell": True,
            "trend_filter": {"enabled": False},
        },
        "broker_sim": {
            "lot_size": 100,
            "fee_rate": 0,
            "min_fee": 0,
            "slippage_pct": 0,
            "fill_mode": "next_bar_open",
        },
        "risk": {
            "max_total_position_pct": 1.0,
            "max_symbol_position_pct": 1.0,
            "min_cash_pct": 0,
            "max_trades_per_symbol_per_day": 10,
            "max_trades_per_day": 10,
            "protect_base_position": True,
        },
        "experiment": {
            "train": {"start_date": "2024-01-01", "end_date": "2024-02-15"},
            "validation": {"start_date": "2024-02-16", "end_date": "2024-04-01"},
            "test": {"start_date": "2024-04-02", "end_date": "2024-05-20"},
            "drawdown_penalty": 0.5,
            "parameter_grid": {"grid_pct": [0.03, 0.05]},
            "walk_forward": {
                "enabled": True,
                "start_date": "2024-01-01",
                "end_date": "2024-05-20",
                "train_months": 1,
                "validation_months": 1,
                "step_months": 1,
            },
        },
    }


def _bars() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-01", periods=105)
    rows = []
    for index, dt in enumerate(dates):
        close = 10 + index * 0.02 + (0.25 if index % 2 else -0.25)
        rows.append(
            {
                "symbol": "510300",
                "name": "沪深300ETF",
                "datetime": dt.strftime("%Y-%m-%d"),
                "open": close,
                "high": close + 0.1,
                "low": close - 0.1,
                "close": close,
                "volume": 1_000_000,
                "amount": close * 1_000_000,
            }
        )
    return pd.DataFrame(rows)


def test_splits_from_config_and_slice_bars() -> None:
    splits = splits_from_config(_config())
    sliced = slice_bars(_bars(), splits[0])

    assert [split.name for split in splits] == ["train", "validation", "test"]
    assert sliced["datetime"].min() == "2024-01-01"
    assert sliced["datetime"].max() <= "2024-02-15"


def test_walk_forward_windows_from_config() -> None:
    windows = walk_forward_windows_from_config(_config())

    assert len(windows) >= 2
    assert windows[0].window == "wf_01"
    assert windows[0].train.start_date == "2024-01-01"
    assert windows[0].validation.start_date == "2024-02-01"


def test_strategy_variants_include_built_ins_and_parameter_grid() -> None:
    names = [name for name, _ in strategy_variants(_config())]

    assert "current" in names
    assert "no_trend_filter" in names
    assert "grid_grid_pct_0.05" in names
    assert "uptrend_slow_sell" in names
    assert "trend_enhanced_base" in names
    assert "adaptive_grid" in names


def test_run_experiment_selects_train_variant_and_reports_all_splits() -> None:
    splits = [ExperimentSplit("train", "2024-01-01", "2024-02-15"), ExperimentSplit("validation", "2024-02-16", "2024-04-01")]
    result = run_experiment(_config(), 50_000, _bars(), splits)

    assert result["selected_variant"]
    assert result["walk_forward"]
    assert result["metrics"]
    assert result["variant_metrics"]
    assert {row["split"] for row in result["rows"]} == {"train", "validation"}
    assert {row["type"] for row in result["rows"]} >= {"strategy", "benchmark"}
    assert [row["split"] for row in result["summary"]] == ["train", "validation"]
    assert any(row["selected_from_train"] for row in result["rows"])
    assert "win_rate" in result["metrics"][0]
    assert any(row["variant"] == result["selected_variant"] for row in result["variant_metrics"])
