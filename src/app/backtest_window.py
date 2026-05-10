"""Helpers for fair backtest window construction."""

from __future__ import annotations

import pandas as pd

from src.universe.filter import select_universe


def prepare_universe_and_bars(bars: pd.DataFrame, universe_config: dict) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Select the ETF universe using only an initial lookback window."""

    if bars.empty:
        return select_universe(bars, universe_config), bars, ""

    frame = bars.copy()
    frame["datetime"] = pd.to_datetime(frame["datetime"])
    dates = sorted(frame["datetime"].dt.normalize().unique())
    lookback_days = int(universe_config.get("selection_lookback_days", 20))
    if len(dates) < lookback_days:
        return select_universe(frame, universe_config), frame, str(dates[-1])[:10] if dates else ""

    as_of_date = str(dates[lookback_days - 1])[:10]
    universe = select_universe(frame, universe_config, as_of_date=as_of_date)
    trading_bars = frame[frame["datetime"] > pd.to_datetime(as_of_date)].copy()
    trading_bars["datetime"] = trading_bars["datetime"].dt.strftime("%Y-%m-%d")
    return universe, trading_bars, as_of_date


def next_bar_entry_date(bars: pd.DataFrame) -> str | None:
    """Return the first date where a next-bar-open strategy can actually fill."""

    if bars.empty:
        return None
    dates = sorted(pd.to_datetime(bars["datetime"]).dt.normalize().unique())
    if len(dates) < 2:
        return None
    return str(dates[1])[:10]
