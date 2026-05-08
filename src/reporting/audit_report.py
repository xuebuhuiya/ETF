"""Strategy audit report generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def build_audit_rows(signals: list[dict], trades: list[dict]) -> list[dict]:
    """Join signal context and fill results into flat audit rows."""

    trades_by_signal_id = {int(trade["signal_id"]): trade for trade in trades if trade.get("signal_id")}
    rows: list[dict] = []

    for signal in signals:
        audit = _loads(signal.get("audit_json"))
        signal_id = int(signal.get("signal_id") or audit.get("signal_id") or 0)
        trade = trades_by_signal_id.get(signal_id)

        rows.append(
            {
                "signal_id": signal_id,
                "symbol": signal["symbol"],
                "name": signal["name"],
                "side": signal["side"],
                "status": signal["status"],
                "reject_reason": signal.get("reject_reason"),
                "signal_date": signal["datetime"],
                "execution_date": (trade or {}).get("datetime") or audit.get("execution_datetime"),
                "signal_price": signal["price"],
                "execution_price": (trade or {}).get("price") or audit.get("execution_price"),
                "quantity": signal["quantity"],
                "reason": signal["reason"],
                "signal_type": audit.get("signal_type"),
                "reference_price": audit.get("reference_price"),
                "buy_threshold": audit.get("buy_threshold"),
                "avg_cost": audit.get("avg_cost"),
                "sell_threshold": audit.get("sell_threshold"),
                "take_profit_pct": audit.get("take_profit_pct"),
                "grid_pct": audit.get("grid_pct"),
                "cash_before_signal": audit.get("cash_before_signal"),
                "total_equity_before_signal": audit.get("total_equity_before_signal"),
                "position_quantity_before_signal": audit.get("position_quantity_before_signal"),
                "base_quantity_before_signal": audit.get("base_quantity_before_signal"),
                "planned_quantity": audit.get("planned_quantity"),
                "cash_before_execution": audit.get("cash_before_execution"),
                "cash_after_execution": audit.get("cash_after_execution"),
                "quantity_before_execution": audit.get("quantity_before_execution"),
                "quantity_after_execution": audit.get("quantity_after_execution"),
                "fee": audit.get("fee"),
                "slippage_amount": audit.get("slippage_amount"),
                "audit_json": signal.get("audit_json"),
            }
        )

    return rows


def write_audit_reports(output_dir: str | Path, signals: list[dict], trades: list[dict]) -> dict[str, Path]:
    """Write CSV and Markdown audit reports."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    rows = build_audit_rows(signals, trades)

    csv_path = output_path / "audit_report.csv"
    md_path = output_path / "audit_report.md"
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    md_path.write_text(_render_markdown(rows), encoding="utf-8-sig")
    return {"audit_report_csv": csv_path, "audit_report_md": md_path}


def _loads(value: Any) -> dict:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


def _render_markdown(rows: list[dict]) -> str:
    total = len(rows)
    filled = sum(1 for row in rows if row["status"] == "filled")
    rejected = sum(1 for row in rows if row["status"] == "rejected")
    pending = sum(1 for row in rows if row["status"] == "pending")

    reject_counts: dict[str, int] = {}
    for row in rows:
        reason = row.get("reject_reason") or ""
        if reason:
            reject_counts[reason] = reject_counts.get(reason, 0) + 1

    lines = [
        "# 策略审计报告",
        "",
        "## 汇总",
        "",
        f"- 信号总数：{total}",
        f"- 已成交：{filled}",
        f"- 已拦截：{rejected}",
        f"- 待成交：{pending}",
        "",
        "## 风控拦截原因",
        "",
    ]

    if reject_counts:
        for reason, count in sorted(reject_counts.items(), key=lambda item: item[1], reverse=True):
            lines.append(f"- `{reason}`：{count}")
    else:
        lines.append("- 无")

    lines.extend(
        [
            "",
            "## 最近 20 条信号",
            "",
            "| 信号日 | 成交日 | ETF | 方向 | 状态 | 信号价 | 成交价 | 触发原因 | 风控 |",
            "| --- | --- | --- | --- | --- | ---: | ---: | --- | --- |",
        ]
    )

    for row in rows[-20:]:
        lines.append(
            "| {signal_date} | {execution_date} | {name} | {side} | {status} | {signal_price} | {execution_price} | {reason} | {reject_reason} |".format(
                signal_date=row.get("signal_date") or "",
                execution_date=row.get("execution_date") or "",
                name=row.get("name") or "",
                side=_side_label(row.get("side")),
                status=_status_label(row.get("status")),
                signal_price=_fmt(row.get("signal_price")),
                execution_price=_fmt(row.get("execution_price")),
                reason=row.get("reason") or "",
                reject_reason=row.get("reject_reason") or "",
            )
        )

    lines.extend(
        [
            "",
            "## 字段说明",
            "",
            "- `signal_date`：策略看到 T 日收盘后产生信号的日期。",
            "- `execution_date`：回测在下一根 K 线开盘执行信号的日期。",
            "- `reference_price`、`buy_threshold`、`sell_threshold`：用于核对买卖触发是否符合规则。",
            "- `cash_before_signal`、`position_quantity_before_signal`：用于核对当时账户状态。",
            "- `reject_reason`：风控拦截原因。",
        ]
    )
    return "\n".join(lines) + "\n"


def _fmt(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _side_label(value: Any) -> str:
    return {"buy": "买入", "sell": "卖出"}.get(str(value), str(value))


def _status_label(value: Any) -> str:
    return {"filled": "已成交", "rejected": "已拦截", "pending": "待成交"}.get(str(value), str(value))
