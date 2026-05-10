"""Run train/validation/test strategy comparison experiments."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.analysis.benchmark import build_buy_hold_curve, summarize_curve
from src.app.backtest_window import next_bar_entry_date, prepare_universe_and_bars
from src.experiment.split import ExperimentSplit, WalkForwardWindow, slice_bars, walk_forward_windows_from_config
from src.experiment.variants import strategy_variants
from src.strategy.grid_t import GridTBacktester


def run_experiment(config: dict, initial_cash: float, bars: pd.DataFrame, splits: list[ExperimentSplit]) -> dict:
    rows = []
    selected_variant = None

    for split in splits:
        split_rows = run_split(config, initial_cash, bars, split)
        rows.extend(split_rows)
        if split.name == "train":
            selected_variant = select_best_train_variant(split_rows)

    for row in rows:
        row["selected_from_train"] = bool(selected_variant and row["variant"] == selected_variant)

    return {
        "rows": rows,
        "summary": build_experiment_summary(rows, selected_variant),
        "walk_forward": run_walk_forward(config, initial_cash, bars, walk_forward_windows_from_config(config)),
        "selected_variant": selected_variant,
    }


def run_split(config: dict, initial_cash: float, bars: pd.DataFrame, split: ExperimentSplit) -> list[dict]:
    split_bars = slice_bars(bars, split)
    universe, trading_bars, universe_as_of_date = prepare_universe_and_bars(split_bars, config["universe"])
    if universe.empty or trading_bars.empty:
        return [
            {
                "split": split.name,
                "variant": "no_data",
                "type": "error",
                "error": "No ETF candidates or trading bars after warmup.",
                "split_start": split.start_date,
                "split_end": split.end_date,
                "universe_as_of_date": universe_as_of_date,
            }
        ]

    benchmark_entry_date = next_bar_entry_date(trading_bars)
    rows = [
        _run_buy_hold_variant(
            split=split,
            name="buy_hold_max_total_position",
            config=config,
            initial_cash=initial_cash,
            bars=trading_bars,
            universe=universe,
            target_position_pct=float(config["risk"]["max_total_position_pct"]),
            entry_date=benchmark_entry_date,
            universe_as_of_date=universe_as_of_date,
        ),
        _run_buy_hold_variant(
            split=split,
            name="buy_hold_full_position",
            config=config,
            initial_cash=initial_cash,
            bars=trading_bars,
            universe=universe,
            target_position_pct=1.0,
            entry_date=benchmark_entry_date,
            universe_as_of_date=universe_as_of_date,
        ),
    ]
    rows.extend(
        _run_strategy_variant(split, name, variant, initial_cash, trading_bars, universe, universe_as_of_date)
        for name, variant in strategy_variants(config)
    )
    return rows


def run_walk_forward(
    config: dict,
    initial_cash: float,
    bars: pd.DataFrame,
    windows: list[WalkForwardWindow],
) -> list[dict]:
    rows = []
    for window in windows:
        train_rows = run_split(config, initial_cash, bars, window.train)
        selected_variant = select_best_strategy_variant(train_rows)
        validation_rows = run_split(config, initial_cash, bars, window.validation)
        benchmark = next(
            (
                row
                for row in validation_rows
                if row.get("type") == "benchmark" and row.get("variant") == "buy_hold_max_total_position"
            ),
            {},
        )
        selected_row = next(
            (row for row in validation_rows if row.get("type") == "strategy" and row.get("variant") == selected_variant),
            None,
        )
        if selected_row is None:
            rows.append(
                {
                    "window": window.window,
                    "selected_variant": selected_variant,
                    "train_start": window.train.start_date,
                    "train_end": window.train.end_date,
                    "validation_start": window.validation.start_date,
                    "validation_end": window.validation.end_date,
                    "error": "Selected variant missing in validation rows.",
                }
            )
            continue
        benchmark_return = float(benchmark.get("total_return") or 0)
        rows.append(
            {
                "window": window.window,
                "selected_variant": selected_variant,
                "train_start": window.train.start_date,
                "train_end": window.train.end_date,
                "validation_start": window.validation.start_date,
                "validation_end": window.validation.end_date,
                "strategy_total_return": selected_row["total_return"],
                "benchmark_total_return": benchmark.get("total_return"),
                "excess_return": round(float(selected_row["total_return"]) - benchmark_return, 6),
                "strategy_max_drawdown": selected_row["max_drawdown"],
                "benchmark_max_drawdown": benchmark.get("max_drawdown"),
                "score": selected_row["score"],
                "trades": selected_row["trades"],
                "signals": selected_row["signals"],
                "rejected": selected_row["rejected"],
                "symbols": selected_row.get("symbols"),
            }
        )
    return rows


def select_best_train_variant(rows: list[dict]) -> str | None:
    strategy_rows = [row for row in rows if row.get("split") == "train" and row.get("type") == "strategy"]
    if not strategy_rows:
        return select_best_strategy_variant(rows)
    return max(strategy_rows, key=lambda row: float(row["score"]))["variant"]


def select_best_strategy_variant(rows: list[dict]) -> str | None:
    strategy_rows = [row for row in rows if row.get("type") == "strategy"]
    if not strategy_rows:
        return None
    return max(strategy_rows, key=lambda row: float(row["score"]))["variant"]


def build_experiment_summary(rows: list[dict], selected_variant: str | None) -> list[dict]:
    if not selected_variant:
        return []
    selected_rows = [row for row in rows if row["variant"] == selected_variant]
    benchmark_by_split = {
        row["split"]: row
        for row in rows
        if row.get("variant") == "buy_hold_max_total_position" and row.get("type") == "benchmark"
    }
    summary = []
    for row in selected_rows:
        benchmark = benchmark_by_split.get(row["split"], {})
        benchmark_return = float(benchmark.get("total_return") or 0)
        summary.append(
            {
                "split": row["split"],
                "selected_variant": selected_variant,
                "strategy_total_return": row["total_return"],
                "benchmark_total_return": benchmark.get("total_return"),
                "excess_return": round(float(row["total_return"]) - benchmark_return, 6),
                "strategy_max_drawdown": row["max_drawdown"],
                "benchmark_max_drawdown": benchmark.get("max_drawdown"),
                "score": row["score"],
                "trades": row["trades"],
                "signals": row["signals"],
                "rejected": row["rejected"],
            }
        )
    return summary


def write_experiment_reports(output_dir: str | Path, result: dict) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    paths = {
        "experiment_comparison_csv": output_path / "experiment_comparison.csv",
        "experiment_summary_csv": output_path / "experiment_summary.csv",
        "experiment_walk_forward_csv": output_path / "experiment_walk_forward.csv",
    }
    pd.DataFrame(result["rows"]).to_csv(paths["experiment_comparison_csv"], index=False, encoding="utf-8-sig")
    pd.DataFrame(result["summary"]).to_csv(paths["experiment_summary_csv"], index=False, encoding="utf-8-sig")
    pd.DataFrame(result.get("walk_forward", [])).to_csv(
        paths["experiment_walk_forward_csv"], index=False, encoding="utf-8-sig"
    )
    return paths


def _run_strategy_variant(
    split: ExperimentSplit,
    name: str,
    config: dict,
    initial_cash: float,
    bars: pd.DataFrame,
    universe: pd.DataFrame,
    universe_as_of_date: str,
) -> dict:
    account = GridTBacktester(config, initial_cash).run(run_id=0, bars=bars, universe=universe)
    final_snapshot = account.snapshots[-1]
    rejected = [signal for signal in account.signals if signal["status"] == "rejected"]
    trend_rejected = [signal for signal in rejected if signal.get("reject_reason") == "trend_filter"]
    total_return = float(final_snapshot["total_return"])
    max_drawdown = float(final_snapshot["max_drawdown"])
    return {
        "split": split.name,
        "split_start": split.start_date,
        "split_end": split.end_date,
        "variant": name,
        "type": "strategy",
        "final_equity": final_snapshot["total_equity"],
        "total_return": final_snapshot["total_return"],
        "max_drawdown": final_snapshot["max_drawdown"],
        "score": _score(total_return, max_drawdown, config),
        "trades": len(account.trades),
        "signals": len(account.signals),
        "rejected": len(rejected),
        "trend_filter_rejected": len(trend_rejected),
        "universe_as_of_date": universe_as_of_date,
        "symbols": ",".join(universe["symbol"].tolist()),
    }


def _run_buy_hold_variant(
    *,
    split: ExperimentSplit,
    name: str,
    config: dict,
    initial_cash: float,
    bars: pd.DataFrame,
    universe: pd.DataFrame,
    target_position_pct: float,
    entry_date: str | None,
    universe_as_of_date: str,
) -> dict:
    curve = build_buy_hold_curve(
        name=name,
        config=config,
        initial_cash=initial_cash,
        bars=bars,
        universe=universe,
        target_position_pct=target_position_pct,
        entry_date=entry_date,
    )
    summary = summarize_curve(curve)
    return {
        "split": split.name,
        "split_start": split.start_date,
        "split_end": split.end_date,
        "variant": name,
        "type": "benchmark",
        "final_equity": summary["final_equity"],
        "total_return": summary["total_return"],
        "max_drawdown": summary["max_drawdown"],
        "score": None,
        "trades": summary["trades"],
        "signals": 0,
        "rejected": 0,
        "trend_filter_rejected": 0,
        "target_position_pct": round(target_position_pct, 4),
        "entry_date": entry_date,
        "universe_as_of_date": universe_as_of_date,
        "symbols": ",".join(universe["symbol"].tolist()),
    }


def _score(total_return: float, max_drawdown: float, config: dict) -> float:
    penalty = float(config.get("experiment", {}).get("drawdown_penalty", 0.5))
    return round(total_return + max_drawdown * penalty, 6)
