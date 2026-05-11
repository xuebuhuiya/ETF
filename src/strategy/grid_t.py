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
        self.grid_levels: dict[str, int] = {}
        self.grid_lots: dict[str, list[dict]] = {}
        self.last_buy_day_index: dict[str, int] = {}
        self.current_day_index = 0

    def run(self, run_id: int, bars: pd.DataFrame, universe: pd.DataFrame) -> SimAccount:
        selected_symbols = set(universe["symbol"].tolist())
        frame = bars[bars["symbol"].isin(selected_symbols)].sort_values(["datetime", "symbol"])
        frame = self._with_trend_columns(frame)

        for day_index, (dt, day_bars) in enumerate(frame.groupby("datetime", sort=True)):
            self.current_day_index = day_index
            dt_string = str(dt)[:10]

            for row in day_bars.itertuples(index=False):
                open_price = float(row.open)
                close_price = float(row.close)
                trend_context = self._trend_context(row, close_price)
                self._execute_pending_at_open(dt_string, row.symbol, open_price)
                self.account.update_price(row.symbol, row.name, close_price)
                self._maybe_initialize_base(run_id, dt_string, row.symbol, row.name, close_price, trend_context)
                self._maybe_increase_base(run_id, dt_string, row.symbol, row.name, close_price, trend_context)
                self._maybe_trade_grid(run_id, dt_string, row.symbol, row.name, close_price, trend_context)

            self.account.record_snapshot(run_id, dt_string)

        return self.account

    def _execute_pending_at_open(self, dt: str, symbol: str, open_price: float) -> None:
        pending = self.pending_by_symbol.pop(symbol, None)
        if pending is None:
            return
        self.account.execute_pending_signal(pending, execution_dt=dt, execution_price=open_price)
        signal = self.account.signals[int(pending["signal_index"])]
        if signal["status"] != "filled":
            return
        if pending["side"] == "buy" and pending["reason"] not in {"initialize_base_position", "increase_base_position"}:
            trade = self.account.trades[-1] if self.account.trades else {}
            self._add_grid_lot(symbol, int(trade.get("quantity", pending["quantity"])), float(trade.get("price", open_price)))
            self.last_buy_day_index[symbol] = self.current_day_index
        elif pending["side"] == "sell":
            self._consume_grid_lots(symbol, int(pending["quantity"]), float(pending["signal_price"]))

    def _maybe_initialize_base(
        self,
        run_id: int,
        dt: str,
        symbol: str,
        name: str,
        price: float,
        trend_context: dict | None = None,
    ) -> None:
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
        audit = self._audit_context(symbol, price, trend_context)
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

    def _maybe_increase_base(
        self,
        run_id: int,
        dt: str,
        symbol: str,
        name: str,
        price: float,
        trend_context: dict | None = None,
    ) -> None:
        config = self.strategy_config.get("trend_enhanced_base", {})
        if not config.get("enabled", False):
            return
        position = self.account.positions.get(symbol)
        if position is None or position.quantity <= 0 or symbol in self.pending_by_symbol:
            return
        if not (trend_context or {}).get("trend_up", False):
            return

        target_pct = float(config.get("uptrend_base_position_pct", self.strategy_config["base_position_pct"]))
        target_budget = self.account.initial_cash * float(self.risk_config["max_symbol_position_pct"]) * target_pct
        target_quantity = self.account.quantity_for_amount(target_budget, price)
        planned_quantity = self.account.round_lot(max(0, target_quantity - int(position.base_quantity)))
        if planned_quantity <= 0:
            return

        audit = self._audit_context(symbol, price, trend_context)
        audit.update(
            {
                "signal_type": "increase_base_position",
                "target_base_position_pct": target_pct,
                "base_quantity": position.base_quantity,
                "target_base_quantity": target_quantity,
                "planned_quantity": planned_quantity,
            }
        )
        self._submit_signal(
            run_id=run_id,
            dt=dt,
            symbol=symbol,
            name=name,
            side="buy",
            price=price,
            quantity=planned_quantity,
            strategy=self.strategy_name,
            reason="increase_base_position",
            base_quantity=target_quantity,
            audit=audit,
        )

    def _maybe_trade_grid(
        self,
        run_id: int,
        dt: str,
        symbol: str,
        name: str,
        price: float,
        trend_context: dict | None = None,
    ) -> None:
        position = self.account.positions.get(symbol)
        if position is None or position.quantity <= 0:
            return
        if symbol in self.pending_by_symbol:
            return

        reference = self.reference_prices.get(symbol, price)
        grid_params = self._effective_grid_params(trend_context)
        grid_pct = grid_params["grid_pct"]
        take_profit_pct = grid_params["take_profit_pct"]
        trade_amount = float(self.strategy_config["trade_amount"])
        quantity = self.account.quantity_for_amount(trade_amount, price)

        if self.strategy_config.get("allow_buy", True) and price <= reference * (1 - grid_pct):
            max_grid_levels = int(self.strategy_config.get("max_grid_levels", 0))
            current_grid_level = self.grid_levels.get(symbol, 0)

            buy_cooldown_days = int(self.strategy_config.get("buy_cooldown_days", 0))
            days_since_last_buy = self._days_since_last_buy(symbol)

            buy_threshold = reference * (1 - grid_pct)
            audit = self._audit_context(symbol, price, trend_context)
            audit.update(
                {
                    "signal_type": "grid_buy",
                    "reference_price": round(reference, 4),
                    "grid_pct": grid_pct,
                    "base_grid_pct": float(self.strategy_config["grid_pct"]),
                    "volatility_multiplier": grid_params["volatility_multiplier"],
                    "buy_threshold": round(buy_threshold, 4),
                    "distance_to_reference_pct": round((price / reference) - 1, 6) if reference else None,
                    "trade_amount": trade_amount,
                    "planned_quantity": quantity,
                    "current_grid_level": current_grid_level,
                    "max_grid_levels": max_grid_levels,
                    "buy_cooldown_days": buy_cooldown_days,
                    "days_since_last_buy": days_since_last_buy,
                }
            )
            if not audit.get("trend_filter_pass", True):
                self.account.record_rejected_signal(
                    run_id=run_id,
                    dt=dt,
                    symbol=symbol,
                    name=name,
                    side="buy",
                    price=price,
                    quantity=quantity,
                    strategy=self.strategy_name,
                    reason=f"grid_buy price <= reference*(1-{grid_pct})",
                    reject_reason="trend_filter",
                    audit=audit,
                )
                return
            if max_grid_levels and current_grid_level >= max_grid_levels:
                self.account.record_rejected_signal(
                    run_id=run_id,
                    dt=dt,
                    symbol=symbol,
                    name=name,
                    side="buy",
                    price=price,
                    quantity=quantity,
                    strategy=self.strategy_name,
                    reason=f"grid_buy price <= reference*(1-{grid_pct})",
                    reject_reason="max_grid_levels",
                    audit=audit,
                )
                return
            if buy_cooldown_days and days_since_last_buy is not None and days_since_last_buy < buy_cooldown_days:
                self.account.record_rejected_signal(
                    run_id=run_id,
                    dt=dt,
                    symbol=symbol,
                    name=name,
                    side="buy",
                    price=price,
                    quantity=quantity,
                    strategy=self.strategy_name,
                    reason=f"grid_buy price <= reference*(1-{grid_pct})",
                    reject_reason="buy_cooldown_days",
                    audit=audit,
                )
                return
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
        eligible_grid_quantity, sell_threshold = self._eligible_grid_sell(symbol, price, take_profit_pct)
        if (
            self.strategy_config.get("allow_sell", True)
            and sellable_t > 0
            and eligible_grid_quantity > 0
        ):
            planned_quantity = min(quantity, sellable_t, eligible_grid_quantity)
            audit = self._audit_context(symbol, price, trend_context)
            audit.update(
                {
                    "signal_type": "grid_sell",
                    "avg_cost": round(position.avg_cost, 4),
                    "take_profit_pct": take_profit_pct,
                    "base_take_profit_pct": float(self.strategy_config["take_profit_pct"]),
                    "sell_threshold": round(sell_threshold, 4),
                    "sell_threshold_basis": "grid_lot_entry_price",
                    "uptrend_sell_multiplier": grid_params["uptrend_sell_multiplier"],
                    "volatility_multiplier": grid_params["volatility_multiplier"],
                    "sellable_t_quantity": sellable_t,
                    "eligible_grid_quantity": eligible_grid_quantity,
                    "grid_lot_count": len(self.grid_lots.get(symbol, [])),
                    "trade_amount": trade_amount,
                    "planned_quantity": planned_quantity,
                    "current_grid_level": self.grid_levels.get(symbol, 0),
                    "max_grid_levels": int(self.strategy_config.get("max_grid_levels", 0)),
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
                reason=f"grid_sell price >= grid_lot_entry*(1+{take_profit_pct})",
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

    def _days_since_last_buy(self, symbol: str) -> int | None:
        last_day = self.last_buy_day_index.get(symbol)
        if last_day is None:
            return None
        return self.current_day_index - last_day

    def _add_grid_lot(self, symbol: str, quantity: int, fill_price: float) -> None:
        if quantity <= 0:
            return
        self.grid_lots.setdefault(symbol, []).append({"quantity": quantity, "entry_price": fill_price})
        self.grid_levels[symbol] = len([lot for lot in self.grid_lots[symbol] if int(lot["quantity"]) > 0])

    def _eligible_grid_sell(self, symbol: str, price: float, take_profit_pct: float) -> tuple[int, float]:
        lots = self.grid_lots.get(symbol, [])
        eligible = [
            lot
            for lot in lots
            if int(lot["quantity"]) > 0 and price >= float(lot["entry_price"]) * (1 + take_profit_pct)
        ]
        if not eligible:
            next_thresholds = [
                float(lot["entry_price"]) * (1 + take_profit_pct)
                for lot in lots
                if int(lot["quantity"]) > 0
            ]
            return 0, min(next_thresholds) if next_thresholds else 0.0
        threshold = min(float(lot["entry_price"]) * (1 + take_profit_pct) for lot in eligible)
        return sum(int(lot["quantity"]) for lot in eligible), threshold

    def _consume_grid_lots(self, symbol: str, quantity: int, signal_price: float) -> None:
        take_profit_pct = float(self.strategy_config["take_profit_pct"])
        remaining = quantity
        updated_lots: list[dict] = []
        for lot in self.grid_lots.get(symbol, []):
            lot_quantity = int(lot["quantity"])
            entry_price = float(lot["entry_price"])
            if remaining > 0 and signal_price >= entry_price * (1 + take_profit_pct):
                sold = min(lot_quantity, remaining)
                lot_quantity -= sold
                remaining -= sold
            if lot_quantity > 0:
                updated_lots.append({"quantity": lot_quantity, "entry_price": entry_price})
        self.grid_lots[symbol] = updated_lots
        self.grid_levels[symbol] = len(updated_lots)

    def _with_trend_columns(self, frame: pd.DataFrame) -> pd.DataFrame:
        if not self._needs_trend_columns():
            return frame

        trend_config = self._trend_window_config()
        ma_short = int(trend_config.get("ma_short", 20))
        ma_long = int(trend_config.get("ma_long", 60))
        frame = frame.copy()
        frame["trend_ma_short"] = frame.groupby("symbol")["close"].transform(
            lambda series: series.rolling(window=ma_short, min_periods=ma_short).mean()
        )
        frame["trend_ma_long"] = frame.groupby("symbol")["close"].transform(
            lambda series: series.rolling(window=ma_long, min_periods=ma_long).mean()
        )
        adaptive_config = self.strategy_config.get("adaptive_grid", {})
        if adaptive_config.get("enabled", False):
            volatility_window = int(adaptive_config.get("volatility_window", 20))
            frame["trend_volatility"] = frame.groupby("symbol")["close"].transform(
                lambda series: series.pct_change().rolling(window=volatility_window, min_periods=volatility_window).std()
            )
        return frame

    def _trend_context(self, row: object, price: float) -> dict:
        trend_config = self.strategy_config.get("trend_filter", {})
        enabled = bool(trend_config.get("enabled", False))
        ma_short = _float_or_none(getattr(row, "trend_ma_short", None))
        ma_long = _float_or_none(getattr(row, "trend_ma_long", None))
        volatility = _float_or_none(getattr(row, "trend_volatility", None))
        trend_windows = self._trend_window_config()
        short_window = int(trend_windows.get("ma_short", 20))
        long_window = int(trend_windows.get("ma_long", 60))
        reasons: list[str] = []
        trend_up = bool(ma_short is not None and ma_long is not None and price > ma_long and ma_short > ma_long)

        if not enabled:
            return {
                "trend_filter_enabled": False,
                "trend_filter_pass": True,
                "trend_filter_status": "disabled",
                "trend_up": trend_up,
                "trend_ma_short_window": short_window,
                "trend_ma_long_window": long_window,
                "trend_ma_short": round(ma_short, 4) if ma_short is not None else None,
                "trend_ma_long": round(ma_long, 4) if ma_long is not None else None,
                "trend_volatility": round(volatility, 6) if volatility is not None else None,
                "price_vs_ma_long_pct": round((price / ma_long) - 1, 6) if ma_long else None,
            }

        if ma_short is None or ma_long is None:
            status = "not_ready"
        else:
            if trend_config.get("block_buy_below_ma_long", True) and price < ma_long:
                require_short_below = trend_config.get("require_short_ma_below_long_ma", True)
                if not require_short_below or ma_short < ma_long:
                    reasons.append("downtrend_below_ma_long")
            if trend_config.get("require_ma_short_above_ma_long", False) and ma_short <= ma_long:
                reasons.append("ma_short_not_above_ma_long")
            status = "blocked" if reasons else "pass"

        return {
            "trend_filter_enabled": True,
            "trend_filter_pass": not reasons,
            "trend_filter_status": status,
            "trend_filter_reason": ",".join(reasons) if reasons else None,
            "trend_up": trend_up,
            "trend_ma_short_window": short_window,
            "trend_ma_long_window": long_window,
            "trend_ma_short": round(ma_short, 4) if ma_short is not None else None,
            "trend_ma_long": round(ma_long, 4) if ma_long is not None else None,
            "trend_volatility": round(volatility, 6) if volatility is not None else None,
            "price_vs_ma_long_pct": round((price / ma_long) - 1, 6) if ma_long else None,
        }

    def _needs_trend_columns(self) -> bool:
        return any(
            [
                self.strategy_config.get("trend_filter", {}).get("enabled", False),
                self.strategy_config.get("slow_sell_in_uptrend", {}).get("enabled", False),
                self.strategy_config.get("trend_enhanced_base", {}).get("enabled", False),
                self.strategy_config.get("adaptive_grid", {}).get("enabled", False),
            ]
        )

    def _trend_window_config(self) -> dict:
        trend_config = self.strategy_config.get("trend_filter", {})
        slow_sell_config = self.strategy_config.get("slow_sell_in_uptrend", {})
        enhanced_base_config = self.strategy_config.get("trend_enhanced_base", {})
        return {
            "ma_short": slow_sell_config.get(
                "ma_short", enhanced_base_config.get("ma_short", trend_config.get("ma_short", 20))
            ),
            "ma_long": slow_sell_config.get(
                "ma_long", enhanced_base_config.get("ma_long", trend_config.get("ma_long", 60))
            ),
        }

    def _effective_grid_params(self, trend_context: dict | None) -> dict:
        grid_pct = float(self.strategy_config["grid_pct"])
        take_profit_pct = float(self.strategy_config["take_profit_pct"])
        context = trend_context or {}

        volatility_multiplier = 1.0
        adaptive_config = self.strategy_config.get("adaptive_grid", {})
        if adaptive_config.get("enabled", False):
            volatility = context.get("trend_volatility")
            base_volatility = float(adaptive_config.get("base_volatility", 0.012))
            if volatility and base_volatility > 0:
                volatility_multiplier = float(volatility) / base_volatility
                volatility_multiplier = max(
                    float(adaptive_config.get("min_multiplier", 0.75)),
                    min(float(adaptive_config.get("max_multiplier", 1.75)), volatility_multiplier),
                )
                grid_pct *= volatility_multiplier
                take_profit_pct *= volatility_multiplier

        uptrend_sell_multiplier = 1.0
        slow_sell_config = self.strategy_config.get("slow_sell_in_uptrend", {})
        if slow_sell_config.get("enabled", False) and context.get("trend_up", False):
            uptrend_sell_multiplier = float(slow_sell_config.get("take_profit_multiplier", 1.8))
            take_profit_pct *= uptrend_sell_multiplier

        return {
            "grid_pct": grid_pct,
            "take_profit_pct": take_profit_pct,
            "volatility_multiplier": round(volatility_multiplier, 6),
            "uptrend_sell_multiplier": round(uptrend_sell_multiplier, 6),
        }

    def _audit_context(self, symbol: str, signal_price: float, trend_context: dict | None = None) -> dict:
        position = self.account.positions.get(symbol)
        audit = {
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
            "current_grid_level": self.grid_levels.get(symbol, 0),
            "grid_lot_count": len(self.grid_lots.get(symbol, [])),
            "max_grid_levels": int(self.strategy_config.get("max_grid_levels", 0)),
            "buy_cooldown_days": int(self.strategy_config.get("buy_cooldown_days", 0)),
            "days_since_last_buy": self._days_since_last_buy(symbol),
        }
        audit.update(trend_context or {})
        return audit


def _float_or_none(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)
