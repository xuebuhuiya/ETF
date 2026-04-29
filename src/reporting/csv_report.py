"""CSV report writer."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_reports(
    output_dir: str | Path,
    *,
    signals: list[dict],
    trades: list[dict],
    positions: list[dict],
    snapshots: list[dict],
    universe: list[dict],
) -> dict[str, Path]:
    """Write strategy outputs to CSV files."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    files = {
        "signals": output_path / "signals.csv",
        "trades": output_path / "trades.csv",
        "positions": output_path / "positions.csv",
        "daily_summary": output_path / "daily_summary.csv",
        "universe": output_path / "universe.csv",
    }

    pd.DataFrame(signals).to_csv(files["signals"], index=False, encoding="utf-8-sig")
    pd.DataFrame(trades).to_csv(files["trades"], index=False, encoding="utf-8-sig")
    pd.DataFrame(positions).to_csv(files["positions"], index=False, encoding="utf-8-sig")
    pd.DataFrame(snapshots).to_csv(files["daily_summary"], index=False, encoding="utf-8-sig")
    pd.DataFrame(universe).to_csv(files["universe"], index=False, encoding="utf-8-sig")

    return files
