import shutil
from pathlib import Path

import pytest

from pipeline.config import load_config

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture()
def cfg(tmp_path):
    """A config that writes all data under a temp dir so tests never touch data/."""
    (tmp_path / "config").mkdir()
    shutil.copy(REPO / "config" / "pipeline.yaml", tmp_path / "config" / "pipeline.yaml")
    c = load_config(tmp_path / "config" / "pipeline.yaml", root=tmp_path)
    c.customers, c.products, c.orders_per_day = 80, 30, 40
    return c
