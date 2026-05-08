"""Grid T strategy backtest loop."""

from __future__ import annotations

import pandas as pd

from src.broker_sim.account import SimAccount


class GridTBacktester:
    """Simple grid strategy for local simulation."""

    strategy_name = "grid_t"

    def __init__(self, config: dict, initial_cash: float) -> None:
        self.config = config
        self.strategy_config = config["strategy"]
        self.risk_config = config["risk"]
        self.account = SimAccount(initial_cash, config["broker_sim"], config["risk"])
        self.reference_prices: dict[str, float] = {}
        self.pending_by_symbol: dict[str, dict] = {}

    def run(self, run_id: int, bars: pd.DataFrame, universe: pd.DataFrame) -> SimAccount:
        selected_symbols = set(universe["symbol"].tolist())
        frame = bars[bars["symbol"].isin(selected_symbols)].sort_values(["datetime", "symbol"])

        for dt, day_bars in frame.groupby("datetime", sort=True):
            dt_string = str(dt)[:10]

            for row in day_bars.itertuples(index=False):
                open_price = float(row.open)
                close_price = float(row.close)
                self._execute_pending_at_open(dt_string, row.symbol, open_price)
                self.account.update_price(row.symbol, row.name, close_price)
                self._maybe_initialize_base(run_id, dt_string, row.symbol, row.name, close_price)
                self._maybe_trade_grid(run_id, dt_string, row.symbol, row.name, close_price)

            self.account.record_snapshot(run_id, dt_string)

        return self.account

    def _execute_pending_at_open(self, dt: str, symbol: str, open_price: float) -> None:
        pending = self.pending_by_symbol.pop(symbol, None)
        if pending is None:
            return
        self.account.execute_pending_signal(pending, execution_dt=dt, execution_price=open_price)

    def _maybe_initialize_base(self, run_id: int, dt: str, symbol: str, name: str, price: float) -> None:
        position = self.account.positions.get(symbol)
        if position and position.base_quantity > 0:
            return
        if symbol in self.pending_by_symbol:
            return

        base_budget = (
            self.account.initial_cash
            * float(self.risk_config["max_symbol_position_pct"])
            * float(self.strategy_config["base_position_pct"])
        )
        quantity = self.account.quantity_for_amount(base_budget, price)
        self.reference_prices[symbol] = price
        self._submit_signal(
            run_id=run_id,
            dt=dt,
            symbol=symbol,
            name=name,
            side="buy",
            price=price,
            quantity=quantity,
            strategy=self.strategy_name,
            reason="initialize_base_position",
            base_quantity=quantity,
        )

    def _maybe_trade_grid(self, run_id: int, dt: str, symbol: str, name: str, price: float) -> None:
        position = self.account.positions.get(symbol)
        if position is None or position.quantity <= 0:
            return
        if symbol in self.pending_by_symbol:
            return

        reference = self.reference_prices.get(symbol, price)
        grid_pct = float(self.strategy_config["grid_pct"])
        take_profit_pct = float(self.strategy_config["take_profit_pct"])
        trade_amount = float(self.strategy_config["trade_amount"])
        quantity = self.account.quantity_for_amount(trade_amount, price)

        if self.strategy_config.get("allow_buy", True) and price <= reference * (1 - grid_pct):
            self._submit_signal(
                run_id=run_id,
                dt=dt,
                symbol=symbol,
                name=name,
                side="buy",
                price=price,
                quantity=quantity,
                strategy=self.strategy_name,
                reason=f"grid_buy price <= reference*(1-{grid_pct})",
            )
            self.reference_prices[symbol] = price
            return

        sellable_t = max(0, position.quantity - position.base_quantity)
        if (
            self.strategy_config.get("allow_sell", True)
            and sellable_t > 0
            and price >= position.avg_cost * (1 + take_profit_pct)
        ):
            self._submit_signal(
                run_id=run_id,
                dt=dt,
                symbol=symbol,
                name=name,
                side="sell",
                price=price,
                quantity=min(quantity, sellable_t),
                strategy=self.strategy_name,
                reason=f"grid_sell price >= avg_cost*(1+{take_profit_pct})",
            )
            self.reference_prices[symbol] = price

    def _submit_signal(self, **kwargs) -> None:
        fill_mode = self.config["broker_sim"].get("fill_mode", "next_bar_open")
        if fill_mode == "next_bar_open":
            pending = self.account.submit_signal(**kwargs)
            self.pending_by_symbol[pending["symbol"]] = pending
            return
        self.account.execute_signal(**kwargs)
