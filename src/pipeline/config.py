"""Configuration loading."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Config:
    raw_dir: Path
    warehouse: Path
    images_dir: Path
    seed: int = 42
    start_date: str = "2026-01-01"
    customers: int = 600
    products: int = 120
    orders_per_day: int = 180
    dirty_rate: float = 0.04
    fx_to_inr: dict[str, float] = field(default_factory=lambda: {"INR": 1.0})
    max_reject_rate: float = 0.08
    max_null_rate: float = 0.0
    min_rows: int = 1

    @property
    def orders_dir(self) -> Path:
        return self.raw_dir / "orders"


def load_config(path: str | Path | None = None, root: Path = ROOT) -> Config:
    path = Path(path) if path else root / "config" / "pipeline.yaml"
    data = yaml.safe_load(path.read_text())
    paths, gen, q = data["paths"], data.get("generate", {}), data.get("quality", {})
    return Config(
        raw_dir=root / paths["raw_dir"],
        warehouse=root / paths["warehouse"],
        images_dir=root / paths["images_dir"],
        seed=gen.get("seed", 42),
        start_date=str(gen.get("start_date", "2026-01-01")),
        customers=gen.get("customers", 600),
        products=gen.get("products", 120),
        orders_per_day=gen.get("orders_per_day", 180),
        dirty_rate=gen.get("dirty_rate", 0.04),
        fx_to_inr=data.get("fx_to_inr", {"INR": 1.0}),
        max_reject_rate=q.get("max_reject_rate", 0.08),
        max_null_rate=q.get("max_null_rate", 0.0),
        min_rows=q.get("min_rows", 1),
    )
