import sqlite3

from pipeline.generate import generate
from pipeline.report import render_all
from pipeline.run import run_pipeline


def counts(cfg):
    con = sqlite3.connect(cfg.warehouse)
    try:
        return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in ("fact_sales", "rejected_orders", "processed_files")}
    finally:
        con.close()


def test_generation_is_deterministic(cfg):
    generate(cfg, days=3)
    first = (cfg.orders_dir / "orders_2026-01-02.csv").read_text()
    (cfg.orders_dir / "orders_2026-01-02.csv").unlink()
    generate(cfg, days=3)
    assert (cfg.orders_dir / "orders_2026-01-02.csv").read_text() == first


def test_end_to_end_incremental_and_idempotent(cfg):
    generate(cfg, days=5)
    s1 = run_pipeline(cfg)
    assert s1.status == "success" and s1.files == 5 and s1.rows_loaded > 0
    after_first = counts(cfg)

    s2 = run_pipeline(cfg)  # nothing new: must be a no-op
    assert s2.status == "no_new_data"
    assert counts(cfg) == after_first

    generate(cfg, days=8)   # three more days arrive
    s3 = run_pipeline(cfg)
    assert s3.status == "success" and s3.files == 3
    final = counts(cfg)
    assert final["processed_files"] == 8
    assert final["fact_sales"] == after_first["fact_sales"] + s3.rows_loaded


def test_quality_gate_rolls_back(cfg):
    cfg.max_reject_rate = 0.0  # every batch has injected bad rows, so this must fail
    generate(cfg, days=2)
    s = run_pipeline(cfg)
    assert s.status == "failed"
    c = counts(cfg)
    assert c["fact_sales"] == 0 and c["processed_files"] == 0  # nothing committed, files retried next run


def test_marts_and_report(cfg):
    generate(cfg, days=10)
    run_pipeline(cfg)
    con = sqlite3.connect(cfg.warehouse)
    days = con.execute("SELECT COUNT(*) FROM mart_daily_revenue").fetchone()[0]
    con.close()
    assert days == 10
    images = render_all(cfg.warehouse, cfg.images_dir)
    assert {p.name for p in images} >= {"architecture.png", "daily_revenue.png", "category_revenue.png",
                                         "rejects_by_reason.png", "run_log_and_quality.png"}
