"""Market regime classification and segmented performance summaries."""

from __future__ import annotations

from collections import defaultdict

import pandas as pd


REGIME_LABELS = {
    "uptrend": "上涨",
    "range": "震荡",
    "downtrend": "下跌",
    "not_ready": "样本不足",
}


def build_market_regimes(
    bars: pd.DataFrame,
    universe: pd.DataFrame,
    *,
    short_window: int = 20,
    long_window: int = 60,
    momentum_window: int = 20,
    up_momentum_pct: float = 0.03,
    down_momentum_pct: float = -0.03,
) -> list[dict]:
    """Classify each day using an equal-weight normalized ETF basket."""

    selected_symbols = universe["symbol"].tolist()
    frame = bars[bars["symbol"].isin(selected_symbols)].sort_values(["symbol", "datetime"]).copy()
    if frame.empty:
        return []

    first_close = frame.groupby("symbol")["close"].transform("first")
    frame["normalized_close"] = frame["close"] / first_close
    market = (
        frame.groupby("datetime", as_index=False)["normalized_close"]
        .mean()
        .rename(columns={"normalized_close": "market_index"})
        .sort_values("datetime")
        .reset_index(drop=True)
    )
    market["ma_short"] = market["market_index"].rolling(window=short_window, min_periods=short_window).mean()
    market["ma_long"] = market["market_index"].rolling(window=long_window, min_periods=long_window).mean()
    market["momentum"] = market["market_index"].pct_change(momentum_window)

    rows: list[dict] = []
    for row in market.itertuples(index=False):
        regime = _classify_regime(
            market_index=float(row.market_index),
            ma_short=_float_or_none(row.ma_short),
            ma_long=_float_or_none(row.ma_long),
            momentum=_float_or_none(row.momentum),
            up_momentum_pct=up_momentum_pct,
            down_momentum_pct=down_momentum_pct,
        )
        rows.append(
            {
                "date": str(row.datetime)[:10],
                "regime": regime,
                "regime_label": REGIME_LABELS[regime],
                "market_index": round(float(row.market_index), 6),
                "ma_short": round(float(row.ma_short), 6) if not pd.isna(row.ma_short) else None,
                "ma_long": round(float(row.ma_long), 6) if not pd.isna(row.ma_long) else None,
                "momentum": round(float(row.momentum), 6) if not pd.isna(row.momentum) else None,
            }
        )
    return rows


def summarize_by_regime(
    *,
    equity_rows: list[dict],
    benchmark_rows: list[dict],
    trades: list[dict],
    regime_rows: list[dict],
) -> list[dict]:
    """Summarize strategy and benchmark returns by market regime."""

    if not equity_rows or not regime_rows:
        return []

    regime_by_date = {row["date"]: row for row in regime_rows}
    benchmark_by_date = {row["date"]: row for row in benchmark_rows}
    trade_count_by_date: dict[str, int] = defaultdict(int)
    for trade in trades:
        trade_count_by_date[str(trade["datetime"])[:10]] += 1

    rows = []
    previous_strategy_equity: float | None = None
    previous_benchmark_equity: float | None = None
    for row in equity_rows:
        date = str(row["date"])[:10]
        regime = regime_by_date.get(date)
        benchmark = benchmark_by_date.get(date)
        strategy_equity = float(row["total_equity"])
        benchmark_equity = float(benchmark["total_equity"]) if benchmark else None
        rows.append(
            {
                "date": date,
                "regime": (regime or {}).get("regime", "not_ready"),
                "regime_label": (regime or {}).get("regime_label", REGIME_LABELS["not_ready"]),
                "strategy_return": 0.0
                if previous_strategy_equity in (None, 0)
                else (strategy_equity / previous_strategy_equity) - 1,
                "benchmark_return": 0.0
                if previous_benchmark_equity in (None, 0) or benchmark_equity is None
                else (benchmark_equity / previous_benchmark_equity) - 1,
                "trade_count": trade_count_by_date.get(date, 0),
            }
        )
        previous_strategy_equity = strategy_equity
        if benchmark_equity is not None:
            previous_benchmark_equity = benchmark_equity

    summaries: list[dict] = []
    order = {"uptrend": 0, "range": 1, "downtrend": 2, "not_ready": 3}
    for regime, group in pd.DataFrame(rows).groupby("regime", sort=False):
        strategy_return, strategy_drawdown = _compound_return_and_drawdown(group["strategy_return"].tolist())
        benchmark_return, benchmark_drawdown = _compound_return_and_drawdown(group["benchmark_return"].tolist())
        summaries.append(
            {
                "regime": regime,
                "regime_label": REGIME_LABELS.get(str(regime), str(regime)),
                "days": int(len(group)),
                "strategy_return": round(strategy_return, 6),
                "benchmark_return": round(benchmark_return, 6),
                "excess_return": round(strategy_return - benchmark_return, 6),
                "strategy_max_drawdown": round(strategy_drawdown, 6),
                "benchmark_max_drawdown": round(benchmark_drawdown, 6),
                "trade_count": int(group["trade_count"].sum()),
            }
        )

    return sorted(summaries, key=lambda item: order.get(item["regime"], 99))


def _classify_regime(
    *,
    market_index: float,
    ma_short: float | None,
    ma_long: float | None,
    momentum: float | None,
    up_momentum_pct: float,
    down_momentum_pct: float,
) -> str:
    if ma_short is None or ma_long is None or momentum is None:
        return "not_ready"
    if market_index >= ma_long and ma_short >= ma_long and momentum >= up_momentum_pct:
        return "uptrend"
    if market_index < ma_long and ma_short < ma_long and momentum <= down_momentum_pct:
        return "downtrend"
    return "range"


def _compound_return_and_drawdown(returns: list[float]) -> tuple[float, float]:
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in returns:
        equity *= 1 + float(value)
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, (equity / peak) - 1)
    return equity - 1, max_drawdown


def _float_or_none(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)
