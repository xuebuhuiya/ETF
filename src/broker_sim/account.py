"""Simulated trading account and order checks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import floor


@dataclass
class Position:
    symbol: str
    name: str
    quantity: int = 0
    base_quantity: int = 0
    avg_cost: float = 0.0
    last_price: float = 0.0

    @property
    def market_value(self) -> float:
        return self.quantity * self.last_price

    @property
    def pnl(self) -> float:
        return (self.last_price - self.avg_cost) * self.quantity if self.quantity else 0.0


class SimAccount:
    """Cash, positions, trade execution, and simple risk checks."""

    def __init__(self, initial_cash: float, broker_config: dict, risk_config: dict) -> None:
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.broker_config = broker_config
        self.risk_config = risk_config
        self.positions: dict[str, Position] = {}
        self.trades: list[dict] = []
        self.signals: list[dict] = []
        self.snapshots: list[dict] = []
        self.trade_count_by_day: dict[str, int] = {}
        self.trade_count_by_symbol_day: dict[tuple[str, str], int] = {}
        self.peak_equity = float(initial_cash)

    @property
    def lot_size(self) -> int:
        return int(self.broker_config["lot_size"])

    def round_lot(self, quantity: int) -> int:
        return int(floor(quantity / self.lot_size) * self.lot_size)

    def quantity_for_amount(self, amount: float, price: float) -> int:
        if price <= 0:
            return 0
        return self.round_lot(int(amount / price))

    def update_price(self, symbol: str, name: str, price: float) -> None:
        position = self.positions.get(symbol)
        if position is None:
            position = Position(symbol=symbol, name=name)
            self.positions[symbol] = position
        position.last_price = float(price)

    def total_market_value(self) -> float:
        return sum(position.market_value for position in self.positions.values())

    def total_equity(self) -> float:
        return self.cash + self.total_market_value()

    def execute_signal(
        self,
        *,
        run_id: int,
        dt: str,
        symbol: str,
        name: str,
        side: str,
        price: float,
        quantity: int,
        strategy: str,
        reason: str,
        base_quantity: int | None = None,
        audit: dict | None = None,
    ) -> None:
        pending = self.submit_signal(
            run_id=run_id,
            dt=dt,
            symbol=symbol,
            name=name,
            side=side,
            price=price,
            quantity=quantity,
            strategy=strategy,
            reason=reason,
            base_quantity=base_quantity,
            audit=audit,
        )
        self.execute_pending_signal(pending, execution_dt=dt, execution_price=price)

    def submit_signal(
        self,
        *,
        run_id: int,
        dt: str,
        symbol: str,
        name: str,
        side: str,
        price: float,
        quantity: int,
        strategy: str,
        reason: str,
        base_quantity: int | None = None,
        audit: dict | None = None,
    ) -> dict:
        """Record a signal without filling it yet."""

        quantity = self.round_lot(quantity)
        signal_id = len(self.signals) + 1
        audit_payload = dict(audit or {})
        audit_payload.update(
            {
                "signal_id": signal_id,
                "signal_datetime": dt,
                "signal_price": round(float(price), 4),
                "planned_fill_mode": self.broker_config.get("fill_mode", "next_bar_open"),
            }
        )
        signal = {
            "signal_id": signal_id,
            "run_id": run_id,
            "datetime": dt,
            "symbol": symbol,
            "name": name,
            "side": side,
            "price": price,
            "quantity": quantity,
            "strategy": strategy,
            "reason": reason,
            "status": "pending",
            "reject_reason": None,
            "audit_json": _to_json(audit_payload),
        }
        self.signals.append(signal)
        return {
            "signal_index": len(self.signals) - 1,
            "signal_id": signal_id,
            "run_id": run_id,
            "signal_dt": dt,
            "symbol": symbol,
            "name": name,
            "side": side,
            "signal_price": price,
            "quantity": quantity,
            "strategy": strategy,
            "reason": reason,
            "base_quantity": base_quantity,
            "audit": audit_payload,
        }

    def record_rejected_signal(
        self,
        *,
        run_id: int,
        dt: str,
        symbol: str,
        name: str,
        side: str,
        price: float,
        quantity: int,
        strategy: str,
        reason: str,
        reject_reason: str,
        audit: dict | None = None,
    ) -> None:
        """Record a strategy-level rejection before a signal is sent for execution."""

        quantity = self.round_lot(quantity)
        signal_id = len(self.signals) + 1
        audit_payload = dict(audit or {})
        audit_payload.update(
            {
                "signal_id": signal_id,
                "signal_datetime": dt,
                "signal_price": round(float(price), 4),
                "execution_status": "rejected",
                "reject_reason": reject_reason,
            }
        )
        self.signals.append(
            {
                "signal_id": signal_id,
                "run_id": run_id,
                "datetime": dt,
                "symbol": symbol,
                "name": name,
                "side": side,
                "price": price,
                "quantity": quantity,
                "strategy": strategy,
                "reason": reason,
                "status": "rejected",
                "reject_reason": reject_reason,
                "audit_json": _to_json(audit_payload),
            }
        )

    def execute_pending_signal(self, pending: dict, execution_dt: str, execution_price: float) -> None:
        """Fill or reject a previously generated signal at the execution price."""

        symbol = pending["symbol"]
        name = pending["name"]
        side = pending["side"]
        quantity = self.round_lot(int(pending["quantity"]))
        price = float(execution_price)

        reject_reason = self._risk_reject_reason(execution_dt, symbol, side, price, quantity)
        status = "rejected" if reject_reason else "filled"

        signal = self.signals[int(pending["signal_index"])]
        signal["status"] = status
        signal["reject_reason"] = reject_reason
        audit_payload = dict(pending.get("audit") or {})
        audit_payload.update(
            {
                "execution_datetime": execution_dt,
                "execution_price": round(price, 4),
                "execution_status": status,
                "reject_reason": reject_reason,
                "cash_before_execution": round(self.cash, 2),
                "total_equity_before_execution": round(self.total_equity(), 2),
            }
        )

        if reject_reason:
            signal["audit_json"] = _to_json(audit_payload)
            return

        slip_pct = float(self.broker_config["slippage_pct"])
        fill_price = price * (1 + slip_pct if side == "buy" else 1 - slip_pct)
        amount = fill_price * quantity
        fee = max(amount * float(self.broker_config["fee_rate"]), float(self.broker_config["min_fee"]))
        slippage = abs(fill_price - price) * quantity

        position = self.positions.setdefault(symbol, Position(symbol=symbol, name=name))
        position.last_price = price
        quantity_before = position.quantity
        avg_cost_before = position.avg_cost

        if side == "buy":
            old_cost = position.avg_cost * position.quantity
            position.quantity += quantity
            position.avg_cost = (old_cost + amount + fee) / position.quantity
            self.cash -= amount + fee
            if pending.get("base_quantity") is not None:
                position.base_quantity = max(position.base_quantity, int(pending["base_quantity"]))
        else:
            position.quantity -= quantity
            self.cash += amount - fee
            if position.quantity == 0:
                position.avg_cost = 0.0

        self.trade_count_by_day[execution_dt] = self.trade_count_by_day.get(execution_dt, 0) + 1
        key = (symbol, execution_dt)
        self.trade_count_by_symbol_day[key] = self.trade_count_by_symbol_day.get(key, 0) + 1
        audit_payload.update(
            {
                "fill_price": round(fill_price, 4),
                "fee": round(fee, 2),
                "slippage_amount": round(slippage, 2),
                "cash_after_execution": round(self.cash, 2),
                "quantity_before_execution": quantity_before,
                "quantity_after_execution": position.quantity,
                "avg_cost_before_execution": round(avg_cost_before, 4),
                "avg_cost_after_execution": round(position.avg_cost, 4),
            }
        )
        signal["audit_json"] = _to_json(audit_payload)

        self.trades.append(
            {
                "signal_id": pending["signal_id"],
                "run_id": pending["run_id"],
                "datetime": execution_dt,
                "signal_datetime": pending["signal_dt"],
                "symbol": symbol,
                "name": name,
                "side": side,
                "signal_price": round(float(pending["signal_price"]), 4),
                "price": round(fill_price, 4),
                "quantity": quantity,
                "amount": round(amount, 2),
                "fee": round(fee, 2),
                "slippage": round(slippage, 2),
                "cash_after": round(self.cash, 2),
                "position_after": position.quantity,
                "reason": f"{pending['reason']} | signal_date={pending['signal_dt']}",
                "audit_json": _to_json(audit_payload),
            }
        )

    def record_snapshot(self, run_id: int, dt: str) -> None:
        equity = self.total_equity()
        self.peak_equity = max(self.peak_equity, equity)
        max_drawdown = 0.0 if self.peak_equity == 0 else (equity / self.peak_equity) - 1
        self.snapshots.append(
            {
                "run_id": run_id,
                "date": dt,
                "cash": round(self.cash, 2),
                "market_value": round(self.total_market_value(), 2),
                "total_equity": round(equity, 2),
                "total_return": round((equity / self.initial_cash) - 1, 6),
                "max_drawdown": round(max_drawdown, 6),
                "trade_count": len(self.trades),
            }
        )

    def position_rows(self, run_id: int) -> list[dict]:
        rows: list[dict] = []
        for position in self.positions.values():
            if position.quantity <= 0:
                continue
            rows.append(
                {
                    "run_id": run_id,
                    "symbol": position.symbol,
                    "name": position.name,
                    "quantity": position.quantity,
                    "base_quantity": position.base_quantity,
                    "avg_cost": round(position.avg_cost, 4),
                    "last_price": round(position.last_price, 4),
                    "market_value": round(position.market_value, 2),
                    "pnl": round(position.pnl, 2),
                }
            )
        return rows

    def _risk_reject_reason(self, dt: str, symbol: str, side: str, price: float, quantity: int) -> str | None:
        if quantity <= 0:
            return "quantity_not_lot_sized"

        max_trades_day = int(self.risk_config["max_trades_per_day"])
        if self.trade_count_by_day.get(dt, 0) >= max_trades_day:
            return "max_trades_per_day"

        max_trades_symbol = int(self.risk_config["max_trades_per_symbol_per_day"])
        if self.trade_count_by_symbol_day.get((symbol, dt), 0) >= max_trades_symbol:
            return "max_trades_per_symbol_per_day"

        amount = price * quantity
        position = self.positions.get(symbol)

        if side == "buy":
            fee = max(amount * float(self.broker_config["fee_rate"]), float(self.broker_config["min_fee"]))
            if self.cash < amount + fee:
                return "insufficient_cash"

            min_cash = self.initial_cash * float(self.risk_config["min_cash_pct"])
            if self.cash - amount - fee < min_cash:
                return "min_cash_pct"

            equity = self.total_equity()
            symbol_value_after = (position.market_value if position else 0.0) + amount
            if symbol_value_after > equity * float(self.risk_config["max_symbol_position_pct"]):
                return "max_symbol_position_pct"

            if self.total_market_value() + amount > equity * float(self.risk_config["max_total_position_pct"]):
                return "max_total_position_pct"

        if side == "sell":
            if position is None or position.quantity < quantity:
                return "insufficient_position"
            if self.risk_config.get("protect_base_position", True):
                if position.quantity - quantity < position.base_quantity:
                    return "base_position_protected"

        return None


def _to_json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
