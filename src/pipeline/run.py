"""Pipeline orchestration: extract -> transform -> validate -> load, one transaction per run."""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import ROOT, Config
from .generate import order_file_date
from .quality import blocking_failures, run_checks
from .transform import build_dim_customer, build_dim_date, build_dim_product, clean_orders

log = logging.getLogger("pipeline")
SQL_DIR = ROOT / "sql"


@dataclass
class RunSummary:
    run_id: int
    status: str
    files: int
    rows_in: int
    rows_loaded: int
    rows_rejected: int
    message: str = ""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript((SQL_DIR / "schema.sql").read_text())
    con.executescript((SQL_DIR / "marts.sql").read_text())
    return con


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def pending_files(con: sqlite3.Connection, orders_dir: Path) -> list[Path]:
    done = {r[0] for r in con.execute("SELECT source_file FROM processed_files")}
    return sorted(p for p in orders_dir.glob("orders_*.csv") if p.name not in done)


def _upsert(con: sqlite3.Connection, table: str, df: pd.DataFrame, key: str) -> None:
    if df.empty:
        return
    cols = list(df.columns)
    placeholders = ",".join("?" for _ in cols)
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != key)
    sql = (f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders}) "
           f"ON CONFLICT({key}) DO UPDATE SET {updates}")
    con.executemany(sql, df.astype(object).where(df.notna(), None).itertuples(index=False, name=None))


def run_pipeline(cfg: Config) -> RunSummary:
    con = connect(cfg.warehouse)
    cur = con.execute("INSERT INTO etl_runs (started_at, status) VALUES (?, 'running')", (_now(),))
    run_id = cur.lastrowid
    con.commit()

    files = pending_files(con, cfg.orders_dir)
    if not files:
        con.execute("UPDATE etl_runs SET finished_at=?, status='no_new_data', message=? WHERE run_id=?",
                    (_now(), "watermark up to date", run_id))
        con.commit()
        con.close()
        log.info("run %s: no new files", run_id)
        return RunSummary(run_id, "no_new_data", 0, 0, 0, 0, "watermark up to date")

    log.info("run %s: %d new order files", run_id, len(files))
    customers = pd.read_csv(cfg.raw_dir / "customers.csv", dtype=str)
    products = pd.DataFrame(json.loads((cfg.raw_dir / "products.json").read_text()))

    frames = []
    for f in files:
        df = pd.read_csv(f, dtype=str, keep_default_na=False, na_values=[""])
        df["source_file"] = f.name
        frames.append(df)
    raw = pd.concat(frames, ignore_index=True)

    # drop rows that were already loaded by an earlier run (late duplicates across files)
    existing = {r[0] for r in con.execute("SELECT order_id FROM fact_sales")}
    raw = raw[~raw["order_id"].isin(existing)]

    clean, rejects = clean_orders(raw.drop(columns="source_file"), products, customers, cfg.fx_to_inr)
    clean = clean.merge(raw[["order_id", "source_file"]].drop_duplicates("order_id"), on="order_id", how="left")
    rejects["source_file"] = _source_for(rejects, raw)

    dim_customer = build_dim_customer(customers)
    dim_product = build_dim_product(products)
    dim_date = build_dim_date(clean["date_key"])

    results = run_checks(clean, rejects, dim_customer, dim_product,
                         max_reject_rate=cfg.max_reject_rate, max_null_rate=cfg.max_null_rate,
                         min_rows=cfg.min_rows)
    con.executemany(
        "INSERT INTO dq_results VALUES (?,?,?,?,?,?)",
        [(run_id, r.name, int(r.passed), r.observed, r.expected, r.severity) for r in results])
    failures = blocking_failures(results)

    if failures:
        msg = "; ".join(f"{r.name}: {r.observed} (expected {r.expected})" for r in failures)
        con.execute("UPDATE etl_runs SET finished_at=?, status='failed', files=?, rows_in=?, rows_rejected=?, "
                    "message=? WHERE run_id=?", (_now(), len(files), len(raw), len(rejects), msg, run_id))
        con.commit()
        con.close()
        log.error("run %s failed data quality: %s", run_id, msg)
        return RunSummary(run_id, "failed", len(files), len(raw), 0, len(rejects), msg)

    try:
        with con:  # single transaction: either the whole batch lands or none of it
            _upsert(con, "dim_customer", dim_customer, "customer_id")
            _upsert(con, "dim_product", dim_product, "product_id")
            _upsert(con, "dim_date", dim_date, "date_key")
            fact = clean.copy()
            fact["order_ts"] = fact["order_ts"].dt.strftime("%Y-%m-%dT%H:%M:%S")
            fact["loaded_run"] = run_id
            _upsert(con, "fact_sales", fact, "order_id")
            con.executemany(
                "INSERT INTO rejected_orders VALUES (?,?,?,?,?)",
                [(run_id, r["source_file"], r.get("order_id"), r["reject_reason"],
                  json.dumps({k: (None if pd.isna(v) else v) for k, v in r.items()
                              if k not in ("reject_reason", "source_file")}))
                 for r in rejects.to_dict("records")])
            con.executemany("INSERT INTO processed_files VALUES (?,?,?)",
                            [(f.name, order_file_date(f), run_id) for f in files])
            con.execute("UPDATE etl_runs SET finished_at=?, status='success', files=?, rows_in=?, rows_loaded=?, "
                        "rows_rejected=? WHERE run_id=?",
                        (_now(), len(files), len(raw), len(clean), len(rejects), run_id))
    finally:
        con.close()
    log.info("run %s: loaded %d rows, rejected %d", run_id, len(clean), len(rejects))
    return RunSummary(run_id, "success", len(files), len(raw), len(clean), len(rejects))


def _source_for(rejects: pd.DataFrame, raw: pd.DataFrame) -> list[str]:
    lookup = raw.drop_duplicates("order_id").set_index("order_id")["source_file"]
    return [lookup.get(oid, "unknown") if isinstance(oid, str) else "unknown" for oid in rejects["order_id"]]
