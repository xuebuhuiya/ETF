"""Performance attribution report for strategy versus buy-and-hold."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.analysis.benchmark import build_buy_hold_curve, summarize_curve
from src.analysis.regime import build_market_regimes, summarize_by_regime


def build_attribution(
    *,
    config: dict,
    initial_cash: float,
    bars: pd.DataFrame,
    universe: pd.DataFrame,
    equity_rows: list[dict],
    trades: list[dict],
    signals: list[dict],
) -> dict:
    """Build summary and detail attribution tables."""

    benchmark_curve = build_buy_hold_curve(
        name="buy_hold_max_total_position",
        config=config,
        initial_cash=initial_cash,
        bars=bars,
        universe=universe,
        target_position_pct=float(config["risk"]["max_total_position_pct"]),
    )
    benchmark_summary = summarize_curve(benchmark_curve)
    regime_rows = build_market_regimes(bars, universe)
    regime_summary = summarize_by_regime(
        equity_rows=equity_rows,
        benchmark_rows=benchmark_curve,
        trades=trades,
        regime_rows=regime_rows,
    )

    final_strategy = equity_rows[-1] if equity_rows else {}
    final_equity = float(final_strategy.get("total_equity", 0.0))
    final_return = float(final_strategy.get("total_return", 0.0))
    benchmark_final_equity = float(benchmark_summary["final_equity"])
    benchmark_return = float(benchmark_summary["total_return"])
    equity_gap = benchmark_final_equity - final_equity

    exposure = _exposure_summary(equity_rows, benchmark_curve)
    by_symbol = _symbol_attribution(trades, bars)
    sell_opportunities = _sell_opportunities(trades, bars)
    rejected_opportunities = _rejected_buy_opportunities(signals, bars, config)
    cost_summary = _cost_summary(trades)

    summary = {
        "strategy_final_equity": round(final_equity, 2),
        "strategy_total_return": round(final_return, 6),
        "benchmark_final_equity": round(benchmark_final_equity, 2),
        "benchmark_total_return": round(benchmark_return, 6),
        "equity_gap_vs_70pct_buy_hold": round(equity_gap, 2),
        "return_gap_vs_70pct_buy_hold": round(benchmark_return - final_return, 6),
        **exposure,
        **cost_summary,
        "sell_count": len(sell_opportunities),
        "sell_end_missed_upside": round(sum(row["end_missed_upside"] for row in sell_opportunities), 2),
        "sell_peak_missed_upside": round(sum(row["peak_missed_upside"] for row in sell_opportunities), 2),
        "rejected_buy_count": len(rejected_opportunities),
        "rejected_buy_end_opportunity": round(sum(row["estimated_end_pnl"] for row in rejected_opportunities), 2),
    }

    return {
        "summary": summary,
        "by_regime": regime_summary,
        "by_symbol": by_symbol,
        "sell_opportunities": sell_opportunities,
        "rejected_buy_opportunities": rejected_opportunities,
    }


def write_attribution_report(output_dir: str | Path, attribution: dict) -> dict[str, Path]:
    """Write attribution CSV files and a Markdown report."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    paths = {
        "attribution_summary_csv": output_path / "attribution_summary.csv",
        "attribution_by_regime_csv": output_path / "attribution_by_regime.csv",
        "attribution_by_symbol_csv": output_path / "attribution_by_symbol.csv",
        "attribution_sell_opportunities_csv": output_path / "attribution_sell_opportunities.csv",
        "attribution_rejected_buys_csv": output_path / "attribution_rejected_buys.csv",
        "attribution_report_md": output_path / "attribution_report.md",
    }

    pd.DataFrame([attribution["summary"]]).to_csv(paths["attribution_summary_csv"], index=False, encoding="utf-8-sig")
    pd.DataFrame(attribution["by_regime"]).to_csv(paths["attribution_by_regime_csv"], index=False, encoding="utf-8-sig")
    pd.DataFrame(attribution["by_symbol"]).to_csv(paths["attribution_by_symbol_csv"], index=False, encoding="utf-8-sig")
    pd.DataFrame(attribution["sell_opportunities"]).to_csv(
        paths["attribution_sell_opportunities_csv"], index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(attribution["rejected_buy_opportunities"]).to_csv(
        paths["attribution_rejected_buys_csv"], index=False, encoding="utf-8-sig"
    )
    paths["attribution_report_md"].write_text(_render_markdown(attribution), encoding="utf-8-sig")
    return paths


def _exposure_summary(equity_rows: list[dict], benchmark_curve: list[dict]) -> dict:
    strategy_exposures = [
        float(row["market_value"]) / float(row["total_equity"])
        for row in equity_rows
        if float(row.get("total_equity") or 0) > 0
    ]
    benchmark_exposures = [
        float(row["market_value"]) / float(row["total_equity"])
        for row in benchmark_curve
        if float(row.get("total_equity") or 0) > 0
    ]
    return {
        "strategy_avg_exposure": round(sum(strategy_exposures) / len(strategy_exposures), 6)
        if strategy_exposures
        else 0.0,
        "benchmark_avg_exposure": round(sum(benchmark_exposures) / len(benchmark_exposures), 6)
        if benchmark_exposures
        else 0.0,
        "strategy_final_exposure": round(strategy_exposures[-1], 6) if strategy_exposures else 0.0,
        "benchmark_final_exposure": round(benchmark_exposures[-1], 6) if benchmark_exposures else 0.0,
    }


def _symbol_attribution(trades: list[dict], bars: pd.DataFrame) -> list[dict]:
    close_by_symbol = _final_close_by_symbol(bars)
    rows = []
    for symbol, symbol_trades in _group_by(trades, "symbol").items():
        final_close = close_by_symbol.get(symbol)
        if final_close is None:
            continue
        current = _evaluate_trade_path(symbol_trades, final_close)
        first_sell_index = next((idx for idx, trade in enumerate(symbol_trades) if trade["side"] == "sell"), None)
        hold_after_sell = (
            _evaluate_trade_path(symbol_trades[: first_sell_index + 1], final_close)
            if first_sell_index is not None
            else current
        )
        rows.append(
            {
                "symbol": symbol,
                "name": symbol_trades[0].get("name", symbol),
                "trade_count": len(symbol_trades),
                "sell_count": sum(1 for trade in symbol_trades if trade["side"] == "sell"),
                "current_quantity": current["quantity"],
                "current_pnl": round(current["pnl"], 2),
                "current_return": round(current["return_pct"], 6) if current["return_pct"] is not None else None,
                "hold_after_first_sell_pnl": round(hold_after_sell["pnl"], 2),
                "hold_after_first_sell_return": round(hold_after_sell["return_pct"], 6)
                if hold_after_sell["return_pct"] is not None
                else None,
                "hold_after_first_sell_diff": round(hold_after_sell["pnl"] - current["pnl"], 2),
                "final_close": round(final_close, 4),
            }
        )
    return sorted(rows, key=lambda row: row["current_pnl"], reverse=True)


def _sell_opportunities(trades: list[dict], bars: pd.DataFrame) -> list[dict]:
    bars_by_symbol = {
        symbol: frame.sort_values("datetime").reset_index(drop=True)
        for symbol, frame in bars.groupby("symbol", sort=False)
    }
    rows = []
    for trade in trades:
        if trade["side"] != "sell":
            continue
        symbol = trade["symbol"]
        frame = bars_by_symbol.get(symbol)
        if frame is None or frame.empty:
            continue
        after = frame[frame["datetime"] >= trade["datetime"]]
        if after.empty:
            continue
        sell_price = float(trade["price"])
        quantity = int(trade["quantity"])
        end_close = float(after.iloc[-1]["close"])
        peak_close = float(after["close"].max())
        rows.append(
            {
                "datetime": trade["datetime"],
                "symbol": symbol,
                "name": trade.get("name", symbol),
                "quantity": quantity,
                "sell_price": round(sell_price, 4),
                "end_close": round(end_close, 4),
                "peak_close_after_sell": round(peak_close, 4),
                "end_missed_upside": round(max(0.0, end_close - sell_price) * quantity, 2),
                "peak_missed_upside": round(max(0.0, peak_close - sell_price) * quantity, 2),
            }
        )
    return sorted(rows, key=lambda row: row["end_missed_upside"], reverse=True)


def _rejected_buy_opportunities(signals: list[dict], bars: pd.DataFrame, config: dict) -> list[dict]:
    bars_by_symbol = {
        symbol: frame.sort_values("datetime").reset_index(drop=True)
        for symbol, frame in bars.groupby("symbol", sort=False)
    }
    slippage_pct = float(config["broker_sim"]["slippage_pct"])
    rows = []
    for signal in signals:
        if signal.get("side") != "buy" or signal.get("status") != "rejected":
            continue
        symbol = signal["symbol"]
        frame = bars_by_symbol.get(symbol)
        if frame is None or frame.empty:
            continue
        after_signal = frame[frame["datetime"] > signal["datetime"]]
        if after_signal.empty:
            continue
        execution_open = float(after_signal.iloc[0]["open"])
        estimated_fill = execution_open * (1 + slippage_pct)
        end_close = float(after_signal.iloc[-1]["close"])
        quantity = int(signal["quantity"])
        rows.append(
            {
                "datetime": signal["datetime"],
                "symbol": symbol,
                "name": signal.get("name", symbol),
                "reject_reason": signal.get("reject_reason"),
                "quantity": quantity,
                "signal_price": round(float(signal["price"]), 4),
                "estimated_fill": round(estimated_fill, 4),
                "end_close": round(end_close, 4),
                "estimated_end_pnl": round((end_close - estimated_fill) * quantity, 2),
                "trend_filter_reason": _loads(signal.get("audit_json")).get("trend_filter_reason"),
            }
        )
    return sorted(rows, key=lambda row: row["estimated_end_pnl"], reverse=True)


def _cost_summary(trades: list[dict]) -> dict:
    return {
        "total_fee": round(sum(float(trade.get("fee") or 0) for trade in trades), 2),
        "total_slippage": round(sum(float(trade.get("slippage") or 0) for trade in trades), 2),
        "trade_count": len(trades),
    }


def _evaluate_trade_path(trades: list[dict], close: float) -> dict:
    quantity = 0
    cash_flow = 0.0
    invested = 0.0
    for trade in trades:
        amount = float(trade.get("amount") or 0)
        fee = float(trade.get("fee") or 0)
        trade_quantity = int(trade.get("quantity") or 0)
        if trade["side"] == "buy":
            quantity += trade_quantity
            cash_flow -= amount + fee
            invested += amount + fee
        else:
            quantity -= trade_quantity
            cash_flow += amount - fee
    pnl = cash_flow + quantity * close
    return {
        "quantity": quantity,
        "pnl": pnl,
        "return_pct": pnl / invested if invested > 0 else None,
    }


def _final_close_by_symbol(bars: pd.DataFrame) -> dict[str, float]:
    rows = bars.sort_values(["symbol", "datetime"]).groupby("symbol", sort=False).tail(1)
    return {row.symbol: float(row.close) for row in rows.itertuples(index=False)}


def _group_by(rows: list[dict], key: str) -> dict[Any, list[dict]]:
    grouped: dict[Any, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row[key], []).append(row)
    return grouped


def _loads(value: Any) -> dict:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


def _render_markdown(attribution: dict) -> str:
    summary = attribution["summary"]
    regime_by_name = {row["regime"]: row for row in attribution["by_regime"]}
    uptrend = regime_by_name.get("uptrend", {})
    range_regime = regime_by_name.get("range", {})
    lines = [
        "# 收益差距归因报告",
        "",
        "## 总结",
        "",
        f"- 策略期末总资产：{summary['strategy_final_equity']:.2f}",
        f"- 70% 买入持有期末总资产：{summary['benchmark_final_equity']:.2f}",
        f"- 策略相对 70% 买入持有少赚：{summary['equity_gap_vs_70pct_buy_hold']:.2f}",
        f"- 策略收益率：{summary['strategy_total_return']:.2%}",
        f"- 70% 买入持有收益率：{summary['benchmark_total_return']:.2%}",
        "",
        "## 结论",
        "",
        f"- 最大差距来自上涨阶段：上涨状态里策略收益 {float(uptrend.get('strategy_return', 0)):.2%}，70% 基准收益 {float(uptrend.get('benchmark_return', 0)):.2%}，超额收益 {float(uptrend.get('excess_return', 0)):.2%}。",
        f"- 策略在震荡阶段反而有优势：震荡状态里策略收益 {float(range_regime.get('strategy_return', 0)):.2%}，70% 基准收益 {float(range_regime.get('benchmark_return', 0)):.2%}，超额收益 {float(range_regime.get('excess_return', 0)):.2%}。",
        f"- 仓位暴露偏低是核心原因之一：策略平均仓位 {summary['strategy_avg_exposure']:.2%}，70% 基准平均仓位 {summary['benchmark_avg_exposure']:.2%}。",
        f"- 交易成本很小：手续费和滑点合计 {summary['total_fee'] + summary['total_slippage']:.2f}，远低于 {summary['equity_gap_vs_70pct_buy_hold']:.2f} 的收益差距。",
        "- 因此当前策略更像低回撤震荡策略，不是上涨趋势增强策略。",
        "",
        "## 主要归因",
        "",
        f"- 平均仓位暴露：策略 {summary['strategy_avg_exposure']:.2%}，70% 基准 {summary['benchmark_avg_exposure']:.2%}。",
        f"- 卖出后到期末的逐笔粗估机会成本上限：{summary['sell_end_missed_upside']:.2f}。",
        f"- 卖出后到后续最高价的逐笔粗估机会成本上限：{summary['sell_peak_missed_upside']:.2f}。",
        f"- 被拒绝买入如果持有到期末的逐笔粗估机会上限：{summary['rejected_buy_end_opportunity']:.2f}。",
        f"- 交易成本：手续费 {summary['total_fee']:.2f}，滑点 {summary['total_slippage']:.2f}。",
        "",
        "## 行情状态",
        "",
        "| 状态 | 天数 | 策略收益 | 70%基准收益 | 超额收益 | 成交次数 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in attribution["by_regime"]:
        lines.append(
            f"| {row['regime_label']} | {row['days']} | {row['strategy_return']:.2%} | {row['benchmark_return']:.2%} | {row['excess_return']:.2%} | {row['trade_count']} |"
        )

    lines.extend(
        [
            "",
            "## ETF 明细",
            "",
            "| ETF | 成交 | 当前策略盈亏 | 首次减仓后不动盈亏 | 差值 |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in attribution["by_symbol"]:
        lines.append(
            f"| {row['name']} | {row['trade_count']} | {row['current_pnl']:.2f} | {row['hold_after_first_sell_pnl']:.2f} | {row['hold_after_first_sell_diff']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## 读法",
            "",
            "- `卖出机会成本` 是逐笔粗估上限：假设卖出的份额如果一直拿到期末或后续最高点，可能多赚多少；如果后来又买回，会重复计算。",
            "- `被拒绝买入机会` 是逐笔粗估上限：假设每个被拦截买入都在下一交易日开盘成交并持有到期末；同一只 ETF 多次拦截会重复计算，不能直接当作真实可追回收益。",
            "- 如果策略明显跑输买入持有，但回撤低很多，说明当前策略更偏风险控制，不是趋势增强策略。",
        ]
    )
    return "\n".join(lines) + "\n"
