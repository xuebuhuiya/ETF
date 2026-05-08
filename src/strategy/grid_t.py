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
        audit = self._audit_context(symbol, price)
        audit.update(
            {
                "signal_type": "initialize_base_position",
                "base_budget": round(base_budget, 2),
                "base_position_pct": float(self.strategy_config["base_position_pct"]),
                "max_symbol_position_pct": float(self.risk_config["max_symbol_position_pct"]),
                "planned_quantity": quantity,
            }
        )
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
            audit=audit,
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
            buy_threshold = reference * (1 - grid_pct)
            audit = self._audit_context(symbol, price)
            audit.update(
                {
                    "signal_type": "grid_buy",
                    "reference_price": round(reference, 4),
                    "grid_pct": grid_pct,
                    "buy_threshold": round(buy_threshold, 4),
                    "distance_to_reference_pct": round((price / reference) - 1, 6) if reference else None,
                    "trade_amount": trade_amount,
                    "planned_quantity": quantity,
                }
            )
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
                audit=audit,
            )
            self.reference_prices[symbol] = price
            return

        sellable_t = max(0, position.quantity - position.base_quantity)
        if (
            self.strategy_config.get("allow_sell", True)
            and sellable_t > 0
            and price >= position.avg_cost * (1 + take_profit_pct)
        ):
            sell_threshold = position.avg_cost * (1 + take_profit_pct)
            planned_quantity = min(quantity, sellable_t)
            audit = self._audit_context(symbol, price)
            audit.update(
                {
                    "signal_type": "grid_sell",
                    "avg_cost": round(position.avg_cost, 4),
                    "take_profit_pct": take_profit_pct,
                    "sell_threshold": round(sell_threshold, 4),
                    "sellable_t_quantity": sellable_t,
                    "trade_amount": trade_amount,
                    "planned_quantity": planned_quantity,
                }
            )
            self._submit_signal(
                run_id=run_id,
                dt=dt,
                symbol=symbol,
                name=name,
                side="sell",
                price=price,
                quantity=planned_quantity,
                strategy=self.strategy_name,
                reason=f"grid_sell price >= avg_cost*(1+{take_profit_pct})",
                audit=audit,
            )
            self.reference_prices[symbol] = price

    def _submit_signal(self, **kwargs) -> None:
        fill_mode = self.config["broker_sim"].get("fill_mode", "next_bar_open")
        if fill_mode == "next_bar_open":
            pending = self.account.submit_signal(**kwargs)
            self.pending_by_symbol[pending["symbol"]] = pending
            return
        self.account.execute_signal(**kwargs)

    def _audit_context(self, symbol: str, signal_price: float) -> dict:
        position = self.account.positions.get(symbol)
        return {
            "signal_price": round(signal_price, 4),
            "fill_mode": self.config["broker_sim"].get("fill_mode", "next_bar_open"),
            "cash_before_signal": round(self.account.cash, 2),
            "total_equity_before_signal": round(self.account.total_equity(), 2),
            "total_market_value_before_signal": round(self.account.total_market_value(), 2),
            "position_quantity_before_signal": position.quantity if position else 0,
            "base_quantity_before_signal": position.base_quantity if position else 0,
            "avg_cost_before_signal": round(position.avg_cost, 4) if position else 0.0,
            "last_price_before_signal": round(position.last_price, 4) if position else 0.0,
            "max_total_position_pct": float(self.risk_config["max_total_position_pct"]),
            "max_symbol_position_pct": float(self.risk_config["max_symbol_position_pct"]),
            "min_cash_pct": float(self.risk_config["min_cash_pct"]),
        }
