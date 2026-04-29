"""Project configuration loading."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class AppConfig:
    """Thin wrapper around the YAML config with path helpers."""

    raw: dict[str, Any]
    root_dir: Path

    @property
    def initial_cash(self) -> float:
        return float(self.raw["capital"]["initial_cash"])

    @property
    def parquet_dir(self) -> Path:
        return self.root_dir / self.raw["data"]["parquet_dir"]

    @property
    def state_db(self) -> Path:
        return self.root_dir / self.raw["storage"]["state_db"]

    @property
    def reporting_dir(self) -> Path:
        return self.root_dir / self.raw["reporting"]["output_dir"]


def load_config(config_path: str | Path = "config/config.example.yaml") -> AppConfig:
    """Load a YAML config relative to the current project root."""

    root_dir = Path.cwd()
    path = Path(config_path)
    if not path.is_absolute():
        path = root_dir / path

    with path.open("r", encoding="utf-8-sig") as file:
        raw = yaml.safe_load(file)

    return AppConfig(raw=raw, root_dir=root_dir)
