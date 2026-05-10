"""Date range splitting for strategy experiments."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ExperimentSplit:
    name: str
    start_date: str
    end_date: str


@dataclass(frozen=True)
class WalkForwardWindow:
    window: str
    train: ExperimentSplit
    validation: ExperimentSplit


def splits_from_config(config: dict) -> list[ExperimentSplit]:
    experiment_config = config.get("experiment", {})
    splits = []
    for name in ("train", "validation", "test"):
        raw = experiment_config.get(name)
        if not raw:
            continue
        splits.append(ExperimentSplit(name=name, start_date=str(raw["start_date"]), end_date=str(raw["end_date"])))
    return splits


def walk_forward_windows_from_config(config: dict) -> list[WalkForwardWindow]:
    raw = config.get("experiment", {}).get("walk_forward", {})
    if not raw or not raw.get("enabled", False):
        return []

    start = pd.Timestamp(str(raw["start_date"]))
    end = pd.Timestamp(str(raw["end_date"]))
    train_months = int(raw.get("train_months", 6))
    validation_months = int(raw.get("validation_months", 3))
    step_months = int(raw.get("step_months", validation_months))

    windows = []
    index = 1
    train_start = start
    while True:
        train_end = train_start + pd.DateOffset(months=train_months) - pd.Timedelta(days=1)
        validation_start = train_end + pd.Timedelta(days=1)
        validation_end = validation_start + pd.DateOffset(months=validation_months) - pd.Timedelta(days=1)
        if validation_end > end:
            break
        window = f"wf_{index:02d}"
        windows.append(
            WalkForwardWindow(
                window=window,
                train=ExperimentSplit(
                    name=f"{window}_train",
                    start_date=train_start.strftime("%Y-%m-%d"),
                    end_date=train_end.strftime("%Y-%m-%d"),
                ),
                validation=ExperimentSplit(
                    name=f"{window}_validation",
                    start_date=validation_start.strftime("%Y-%m-%d"),
                    end_date=validation_end.strftime("%Y-%m-%d"),
                ),
            )
        )
        index += 1
        train_start = train_start + pd.DateOffset(months=step_months)
    return windows


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
