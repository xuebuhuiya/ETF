"""Buy-and-hold benchmark calculations."""

from __future__ import annotations

import pandas as pd


def build_buy_hold_curve(
    *,
    name: str,
    config: dict,
    initial_cash: float,
    bars: pd.DataFrame,
    universe: pd.DataFrame,
    target_position_pct: float,
    entry_date: str | None = None,
) -> list[dict]:
    """Build a daily equal-weight buy-and-hold equity curve."""

    selected_symbols = universe["symbol"].tolist()
    frame = bars[bars["symbol"].isin(selected_symbols)].sort_values(["datetime", "symbol"])
    entry_frame = frame
    if entry_date:
        entry_frame = frame[pd.to_datetime(frame["datetime"]) >= pd.to_datetime(entry_date)]
    first_bars = entry_frame.sort_values(["symbol", "datetime"]).groupby("symbol", sort=False).first()

    broker_config = config["broker_sim"]
    lot_size = int(broker_config["lot_size"])
    fee_rate = float(broker_config["fee_rate"])
    min_fee = float(broker_config["min_fee"])
    slippage_pct = float(broker_config["slippage_pct"])

    cash = float(initial_cash)
    holdings: dict[str, int] = {}
    buy_budget = initial_cash * target_position_pct / max(len(selected_symbols), 1)
    trades = 0

    has_entered = False

    def enter_positions() -> None:
        nonlocal cash, trades, has_entered
        if has_entered:
            return
        for symbol in selected_symbols:
            if symbol not in first_bars.index:
                continue
            fill_price = float(first_bars.loc[symbol, "open"]) * (1 + slippage_pct)
            quantity = quantity_for_budget(buy_budget, fill_price, lot_size, fee_rate, min_fee)
            amount = fill_price * quantity
            fee = max(amount * fee_rate, min_fee) if quantity else 0.0
            if quantity and cash >= amount + fee:
                holdings[symbol] = quantity
                cash -= amount + fee
                trades += 1
        has_entered = True

    if entry_date is None:
        enter_positions()

    rows: list[dict] = []
    last_prices = {symbol: 0.0 for symbol in selected_symbols}
    peak_equity = float(initial_cash)

    for dt, day_bars in frame.groupby("datetime", sort=True):
        if entry_date and pd.to_datetime(dt) >= pd.to_datetime(entry_date):
            enter_positions()
        for row in day_bars.itertuples(index=False):
            last_prices[row.symbol] = float(row.close)
        market_value = sum(quantity * last_prices.get(symbol, 0.0) for symbol, quantity in holdings.items())
        total_equity = cash + market_value
        peak_equity = max(peak_equity, total_equity)
        max_drawdown = 0.0 if peak_equity == 0 else (total_equity / peak_equity) - 1
        rows.append(
            {
                "variant": name,
                "date": str(dt)[:10],
                "cash": round(cash, 2),
                "market_value": round(market_value, 2),
                "total_equity": round(total_equity, 2),
                "total_return": round((total_equity / initial_cash) - 1, 6),
                "max_drawdown": round(max_drawdown, 6),
                "trade_count": trades,
                "target_position_pct": round(target_position_pct, 4),
            }
        )

    return rows


def summarize_curve(curve: list[dict]) -> dict:
    """Return final metrics for a benchmark curve."""

    if not curve:
        return {
            "final_equity": 0.0,
            "total_return": 0.0,
            "max_drawdown": 0.0,
            "trades": 0,
        }
    final_row = curve[-1]
    return {
        "final_equity": final_row["total_equity"],
        "total_return": final_row["total_return"],
        "max_drawdown": min(row["max_drawdown"] for row in curve),
        "trades": final_row["trade_count"],
    }


def quantity_for_budget(budget: float, price: float, lot_size: int, fee_rate: float, min_fee: float) -> int:
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
