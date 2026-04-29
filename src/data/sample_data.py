"""Deterministic sample ETF bars for local validation."""

from __future__ import annotations

import math
from datetime import date

import pandas as pd


SAMPLE_ETFS = [
    ("510300", "沪深300ETF", 3.85, 130_000_000),
    ("510500", "中证500ETF", 5.75, 95_000_000),
    ("159915", "创业板ETF", 1.95, 160_000_000),
    ("518880", "黄金ETF", 4.95, 75_000_000),
    ("588000", "科创50ETF", 0.92, 145_000_000),
]


def generate_sample_bars(start: str = "2024-01-01", periods: int = 120) -> pd.DataFrame:
    """Generate business-day OHLCV bars with enough movement for strategy tests."""

    dates = pd.bdate_range(start=start, periods=periods)
    rows: list[dict] = []

    for symbol_index, (symbol, name, base_price, base_amount) in enumerate(SAMPLE_ETFS):
        last_close = base_price
        phase = symbol_index * 0.7
        for i, dt in enumerate(dates):
            cycle = math.sin(i / 3.0 + phase)
            slower_cycle = math.sin(i / 11.0 + phase / 2)
            drift = 1 + 0.0015 * i / max(periods, 1)
            close = base_price * drift * (1 + 0.06 * cycle + 0.035 * slower_cycle)
            open_price = last_close * (1 + 0.004 * math.sin(i / 3.0 + phase))
            high = max(open_price, close) * (1 + 0.004 + 0.002 * abs(cycle))
            low = min(open_price, close) * (1 - 0.004 - 0.002 * abs(slower_cycle))
            volume = int(base_amount / close * (0.9 + 0.2 * abs(cycle)))
            amount = float(volume * close)

            rows.append(
                {
                    "symbol": symbol,
                    "name": name,
                    "datetime": dt.strftime("%Y-%m-%d"),
                    "open": round(open_price, 4),
                    "high": round(high, 4),
                    "low": round(low, 4),
                    "close": round(close, 4),
                    "volume": volume,
                    "amount": round(amount, 2),
                    "source": "sample",
                    "adjust": "none",
                }
            )
            last_close = close

    return pd.DataFrame(rows)


def today_string() -> str:
    return date.today().isoformat()
