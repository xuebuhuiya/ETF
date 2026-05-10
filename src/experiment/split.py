"""Date range splitting for strategy experiments."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ExperimentSplit:
    name: str
    start_date: str
    end_date: str


def splits_from_config(config: dict) -> list[ExperimentSplit]:
    experiment_config = config.get("experiment", {})
    splits = []
    for name in ("train", "validation", "test"):
        raw = experiment_config.get(name)
        if not raw:
            continue
        splits.append(ExperimentSplit(name=name, start_date=str(raw["start_date"]), end_date=str(raw["end_date"])))
    return splits


def slice_bars(bars: pd.DataFrame, split: ExperimentSplit) -> pd.DataFrame:
    if bars.empty:
        return bars.copy()
    frame = bars.copy()
    frame["datetime"] = pd.to_datetime(frame["datetime"])
    mask = (frame["datetime"] >= pd.to_datetime(split.start_date)) & (
        frame["datetime"] <= pd.to_datetime(split.end_date)
    )
    frame = frame[mask].copy()
    frame["datetime"] = frame["datetime"].dt.strftime("%Y-%m-%d")
    return frame
