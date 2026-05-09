"""Compare strategy parameter variants on cached local market data."""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path

import pandas as pd

from src.config import load_config
from src.storage.parquet_store import ParquetMarketStore
from src.strategy.grid_t import GridTBacktester
from src.universe.filter import select_universe


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare ETF strategy parameter variants.")
    parser.add_argument("--config", default="config/config.example.yaml", help="Path to YAML config.")
    parser.add_argument("--output", default="reports/strategy_comparison.csv", help="CSV output path.")
    args = parser.parse_args()

    cfg = load_config(args.config)
    market_store = ParquetMarketStore(cfg.parquet_dir)
    bars = market_store.read_bars(
        interval=cfg.raw["data"]["bar_interval"],
        start_date=cfg.raw["data"]["start_date"],
        end_date=cfg.raw["data"]["end_date"],
    )
    universe = select_universe(bars, cfg.raw["universe"])
    if universe.empty:
        raise RuntimeError("No ETF candidates selected. Run a backtest and check universe thresholds.")

    rows = [
        _run_buy_hold_variant(
            "buy_hold_max_total_position",
            cfg.raw,
            cfg.initial_cash,
            bars,
            universe,
            target_position_pct=float(cfg.raw["risk"]["max_total_position_pct"]),
        ),
        _run_buy_hold_variant(
            "buy_hold_full_position",
            cfg.raw,
            cfg.initial_cash,
            bars,
            universe,
            target_position_pct=1.0,
        ),
    ]
    rows.extend(_run_strategy_variant(name, variant, cfg.initial_cash, bars, universe) for name, variant in _variants(cfg.raw))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig")

    print(pd.DataFrame(rows).to_string(index=False))
    print(f"comparison_csv: {output_path}")


def _variants(base_config: dict) -> list[tuple[str, dict]]:
    no_trend = deepcopy(base_config)
    no_trend["strategy"]["trend_filter"] = {"enabled": False}

    current = deepcopy(base_config)

    strict = deepcopy(base_config)
    strict["strategy"]["trend_filter"] = {
        "enabled": True,
        "ma_short": 20,
        "ma_long": 60,
        "block_buy_below_ma_long": True,
        "require_short_ma_below_long_ma": False,
        "require_ma_short_above_ma_long": False,
    }

    return [
        ("no_trend_filter", no_trend),
        ("confirmed_downtrend_filter", current),
        ("strict_below_ma_long_filter", strict),
    ]


def _run_strategy_variant(name: str, config: dict, initial_cash: float, bars: pd.DataFrame, universe: pd.DataFrame) -> dict:
    account = GridTBacktester(config, initial_cash).run(run_id=0, bars=bars, universe=universe)
    final_snapshot = account.snapshots[-1]
    rejected = [signal for signal in account.signals if signal["status"] == "rejected"]
    trend_rejected = [signal for signal in rejected if signal.get("reject_reason") == "trend_filter"]
    return {
        "variant": name,
        "type": "strategy",
        "final_equity": final_snapshot["total_equity"],
        "total_return": final_snapshot["total_return"],
        "max_drawdown": final_snapshot["max_drawdown"],
        "trades": len(account.trades),
        "signals": len(account.signals),
        "rejected": len(rejected),
        "trend_filter_rejected": len(trend_rejected),
    }


def _run_buy_hold_variant(
    name: str,
    config: dict,
    initial_cash: float,
    bars: pd.DataFrame,
    universe: pd.DataFrame,
    target_position_pct: float,
) -> dict:
    selected_symbols = universe["symbol"].tolist()
    frame = bars[bars["symbol"].isin(selected_symbols)].sort_values(["datetime", "symbol"])
    first_bars = frame.sort_values(["symbol", "datetime"]).groupby("symbol", sort=False).first()

    broker_config = config["broker_sim"]
    lot_size = int(broker_config["lot_size"])
    fee_rate = float(broker_config["fee_rate"])
    min_fee = float(broker_config["min_fee"])
    slippage_pct = float(broker_config["slippage_pct"])

    cash = float(initial_cash)
    holdings: dict[str, int] = {}
    buy_budget = initial_cash * target_position_pct / max(len(selected_symbols), 1)
    trades = 0

    for symbol in selected_symbols:
        if symbol not in first_bars.index:
            continue
        fill_price = float(first_bars.loc[symbol, "open"]) * (1 + slippage_pct)
        quantity = _quantity_for_budget(buy_budget, fill_price, lot_size, fee_rate, min_fee)
        amount = fill_price * quantity
        fee = max(amount * fee_rate, min_fee) if quantity else 0.0
        if quantity and cash >= amount + fee:
            holdings[symbol] = quantity
            cash -= amount + fee
            trades += 1

    last_prices = {symbol: 0.0 for symbol in selected_symbols}
    peak_equity = float(initial_cash)
    max_drawdown = 0.0
    final_equity = float(initial_cash)

    for _, day_bars in frame.groupby("datetime", sort=True):
        for row in day_bars.itertuples(index=False):
            last_prices[row.symbol] = float(row.close)
        market_value = sum(quantity * last_prices.get(symbol, 0.0) for symbol, quantity in holdings.items())
        final_equity = cash + market_value
        peak_equity = max(peak_equity, final_equity)
        drawdown = 0.0 if peak_equity == 0 else (final_equity / peak_equity) - 1
        max_drawdown = min(max_drawdown, drawdown)

    return {
        "variant": name,
        "type": "benchmark",
        "final_equity": round(final_equity, 2),
        "total_return": round((final_equity / initial_cash) - 1, 6),
        "max_drawdown": round(max_drawdown, 6),
        "trades": trades,
        "signals": 0,
        "rejected": 0,
        "trend_filter_rejected": 0,
        "target_position_pct": round(target_position_pct, 4),
    }


def _quantity_for_budget(budget: float, price: float, lot_size: int, fee_rate: float, min_fee: float) -> int:
    if price <= 0 or budget <= 0:
        return 0
    quantity = int(budget / price / lot_size) * lot_size
    while quantity > 0:
        amount = price * quantity
        fee = max(amount * fee_rate, min_fee)
        if amount + fee <= budget:
            return quantity
        quantity -= lot_size
    return 0


if __name__ == "__main__":
    main()
