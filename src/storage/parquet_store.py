"""Parquet market data store queried through DuckDB."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import duckdb
import pandas as pd


class ParquetMarketStore:
    """Store OHLCV bars in Parquet and query them with DuckDB."""

    def __init__(self, parquet_dir: str | Path) -> None:
        self.parquet_dir = Path(parquet_dir)

    def bars_path(self, interval: str) -> Path:
        return self.parquet_dir / f"bars_{interval}.parquet"

    def write_bars(self, bars: pd.DataFrame, interval: str = "1d") -> Path:
        self.parquet_dir.mkdir(parents=True, exist_ok=True)
        path = self.bars_path(interval)
        ordered = bars.sort_values(["symbol", "datetime"]).reset_index(drop=True)
        ordered.to_parquet(path, index=False)
        return path

    def read_bars(
        self,
        symbols: Sequence[str] | None = None,
        interval: str = "1d",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        path = self.bars_path(interval)
        if not path.exists():
            raise FileNotFoundError(f"Parquet bars not found: {path}")

        where: list[str] = []
        params: list[object] = []

        if symbols:
            placeholders = ", ".join("?" for _ in symbols)
            where.append(f"symbol IN ({placeholders})")
            params.extend(symbols)
        if start_date:
            where.append("datetime >= ?")
            params.append(start_date)
        if end_date:
            where.append("datetime <= ?")
            params.append(end_date)

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        sql = f"""
            SELECT *
            FROM read_parquet(?)
            {where_sql}
            ORDER BY symbol, datetime
        """
        return duckdb.execute(sql, [str(path), *params]).df()
