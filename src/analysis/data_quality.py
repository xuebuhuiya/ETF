"""Market data quality checks for ETF bars."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = ["open", "high", "low", "close", "volume", "amount"]


def build_data_quality_rows(
    bars: pd.DataFrame,
    *,
    selection_lookback_days: int = 20,
) -> list[dict]:
    if bars.empty:
        return []

    frame = bars.copy()
    frame["datetime"] = pd.to_datetime(frame["datetime"])
    rows = []
    for (symbol, name), group in frame.groupby(["symbol", "name"], sort=False):
        group = group.sort_values("datetime")
        duplicate_dates = int(group["datetime"].duplicated().sum())
        missing_by_column = {column: int(group[column].isna().sum()) for column in REQUIRED_COLUMNS if column in group}
        missing_total = sum(missing_by_column.values())
        row_count = int(len(group))
        start_date = group["datetime"].min()
        end_date = group["datetime"].max()
        expected_days = max(1, len(pd.bdate_range(start_date, end_date)))
        completeness = row_count / expected_days
        rows.append(
            {
                "symbol": symbol,
                "name": name,
                "row_count": row_count,
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
                "expected_business_days": expected_days,
                "data_completeness": round(completeness, 6),
                "missing_required_values": missing_total,
                "missing_detail": ";".join(
                    f"{column}:{count}" for column, count in missing_by_column.items() if count > 0
                ),
                "duplicate_dates": duplicate_dates,
                "enough_for_universe": row_count >= selection_lookback_days and missing_total == 0 and duplicate_dates == 0,
            }
        )
    return sorted(rows, key=lambda row: row["symbol"])


def summarize_data_quality(rows: list[dict]) -> dict:
    if not rows:
        return {
            "symbol_count": 0,
            "eligible_symbol_count": 0,
            "symbols_with_missing_values": 0,
            "symbols_with_duplicate_dates": 0,
            "average_completeness": 0.0,
        }
    return {
        "symbol_count": len(rows),
        "eligible_symbol_count": sum(1 for row in rows if row["enough_for_universe"]),
        "symbols_with_missing_values": sum(1 for row in rows if int(row["missing_required_values"]) > 0),
        "symbols_with_duplicate_dates": sum(1 for row in rows if int(row["duplicate_dates"]) > 0),
        "average_completeness": round(
            sum(float(row["data_completeness"]) for row in rows) / len(rows),
            6,
        ),
    }


def write_data_quality_report(output_dir: str | Path, rows: list[dict]) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    paths = {
        "data_quality_csv": output_path / "data_quality.csv",
        "data_quality_md": output_path / "data_quality.md",
    }
    pd.DataFrame(rows).to_csv(paths["data_quality_csv"], index=False, encoding="utf-8-sig")
    paths["data_quality_md"].write_text(_render_markdown(rows), encoding="utf-8-sig")
    return paths


def _render_markdown(rows: list[dict]) -> str:
    summary = summarize_data_quality(rows)
    lines = [
        "# ETF 数据质量报告",
        "",
        "## 总览",
        "",
        f"- ETF 数量：{summary['symbol_count']}",
        f"- 满足初始筛选数据要求：{summary['eligible_symbol_count']}",
        f"- 存在缺失值的 ETF：{summary['symbols_with_missing_values']}",
        f"- 存在重复日期的 ETF：{summary['symbols_with_duplicate_dates']}",
        f"- 平均完整度：{summary['average_completeness']:.2%}",
        "",
        "## 明细",
        "",
        "| ETF | 名称 | 天数 | 起始 | 结束 | 完整度 | 缺失值 | 重复日期 | 可参与筛选 |",
        "| --- | --- | ---: | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            "| {symbol} | {name} | {row_count} | {start_date} | {end_date} | {data_completeness:.2%} | {missing_required_values} | {duplicate_dates} | {eligible} |".format(
                **row,
                eligible="是" if row["enough_for_universe"] else "否",
            )
        )
    return "\n".join(lines) + "\n"
