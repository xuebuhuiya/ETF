"""Strategy variants used by train/validation/test experiments."""

from __future__ import annotations

from copy import deepcopy
from itertools import product


def strategy_variants(base_config: dict) -> list[tuple[str, dict]]:
    """Return conservative built-in variants plus optional parameter-grid variants."""

    variants = _built_in_variants(base_config)
    variants.extend(_grid_variants(base_config))
    return _dedupe_variants(variants)


def _built_in_variants(base_config: dict) -> list[tuple[str, dict]]:
    current = deepcopy(base_config)

    no_trend = deepcopy(base_config)
    no_trend["strategy"]["trend_filter"] = {"enabled": False}

    strict = deepcopy(base_config)
    strict["strategy"]["trend_filter"] = {
        "enabled": True,
        "ma_short": 20,
        "ma_long": 60,
        "block_buy_below_ma_long": True,
        "require_short_ma_below_long_ma": False,
        "require_ma_short_above_ma_long": False,
    }

    higher_exposure = deepcopy(base_config)
    higher_exposure["risk"]["max_total_position_pct"] = min(1.0, float(base_config["risk"]["max_total_position_pct"]) + 0.15)
    higher_exposure["strategy"]["base_position_pct"] = min(1.0, float(base_config["strategy"]["base_position_pct"]) + 0.2)

    slower_sell = deepcopy(base_config)
    slower_sell["strategy"]["take_profit_pct"] = float(base_config["strategy"]["take_profit_pct"]) * 1.5

    uptrend_slow_sell = deepcopy(base_config)
    uptrend_slow_sell["strategy"]["slow_sell_in_uptrend"] = {
        "enabled": True,
        "ma_short": 20,
        "ma_long": 60,
        "take_profit_multiplier": 2.0,
    }

    trend_enhanced_base = deepcopy(base_config)
    trend_enhanced_base["strategy"]["trend_enhanced_base"] = {
        "enabled": True,
        "ma_short": 20,
        "ma_long": 60,
        "uptrend_base_position_pct": 0.85,
    }

    adaptive_grid = deepcopy(base_config)
    adaptive_grid["strategy"]["adaptive_grid"] = {
        "enabled": True,
        "volatility_window": 20,
        "base_volatility": 0.012,
        "min_multiplier": 0.75,
        "max_multiplier": 1.75,
    }

    return [
        ("current", current),
        ("no_trend_filter", no_trend),
        ("strict_below_ma_long_filter", strict),
        ("higher_exposure", higher_exposure),
        ("slower_sell", slower_sell),
        ("uptrend_slow_sell", uptrend_slow_sell),
        ("trend_enhanced_base", trend_enhanced_base),
        ("adaptive_grid", adaptive_grid),
    ]


def _grid_variants(base_config: dict) -> list[tuple[str, dict]]:
    grid_config = base_config.get("experiment", {}).get("parameter_grid", {})
    if not grid_config:
        return []

    keys = [key for key, values in grid_config.items() if values]
    variants = []
    for values in product(*(grid_config[key] for key in keys)):
        variant = deepcopy(base_config)
        name_parts = ["grid"]
        for key, value in zip(keys, values, strict=True):
            if key in variant["strategy"]:
                variant["strategy"][key] = value
            elif key in variant["risk"]:
                variant["risk"][key] = value
            else:
                continue
            name_parts.append(f"{key}_{value}")
        variants.append(("_".join(name_parts), variant))
    return variants


def _dedupe_variants(variants: list[tuple[str, dict]]) -> list[tuple[str, dict]]:
    seen = set()
    deduped = []
    for name, config in variants:
        if name in seen:
            continue
        seen.add(name)
        deduped.append((name, config))
    return deduped
