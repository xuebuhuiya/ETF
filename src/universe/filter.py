"""ETF universe filtering."""

from __future__ import annotations

import pandas as pd


UNIVERSE_COLUMNS = ["symbol", "name", "avg_amount_20d", "volatility_20d", "last_price", "rank"]


def select_universe(bars: pd.DataFrame, universe_config: dict, as_of_date: str | None = None) -> pd.DataFrame:
    """Select ETF candidates from OHLCV bars using liquidity and volatility rules."""

    if bars.empty:
        return pd.DataFrame(columns=UNIVERSE_COLUMNS)

    frame = bars.copy()
    frame["datetime"] = pd.to_datetime(frame["datetime"])
    if as_of_date:
        frame = frame[frame["datetime"] <= pd.to_datetime(as_of_date)]

    rows: list[dict] = []
    for (symbol, name), group in frame.groupby(["symbol", "name"]):
        group = group.sort_values("datetime").tail(20)
        if len(group) < 20:
            continue

        returns = group["close"].pct_change().dropna()
        avg_amount = float(group["amount"].mean())
        volatility = float(returns.std())
        last_price = float(group["close"].iloc[-1])

        if last_price < float(universe_config["min_price"]):
            continue
        if avg_amount < float(universe_config["min_avg_amount_20d"]):
            continue
        if volatility < float(universe_config["min_volatility_20d"]):
            continue
        if volatility > float(universe_config["max_volatility_20d"]):
            continue

        rows.append(
            {
                "symbol": symbol,
                "name": name,
                "avg_amount_20d": avg_amount,
                "volatility_20d": volatility,
                "last_price": last_price,
            }
        )

    selected = pd.DataFrame(rows)
    if selected.empty:
        return pd.DataFrame(columns=UNIVERSE_COLUMNS)

    selected = selected.sort_values("avg_amount_20d", ascending=False).head(
        int(universe_config["max_candidates"])
    )
    selected = selected.reset_index(drop=True)
    selected["rank"] = selected.index + 1
    return selected
