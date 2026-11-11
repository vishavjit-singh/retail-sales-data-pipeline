"""Synthetic source-system generator.

Produces the three raw feeds the pipeline ingests:
  * customers.csv  (CRM export)
  * products.json  (catalogue API dump)
  * orders/orders_YYYY-MM-DD.csv  (one file per day from the order service)

Each day's file is seeded from the base seed plus the day index, so generating
more days later never changes files that already exist. A configurable share of
order rows is deliberately corrupted (duplicates, bad quantities, unknown keys,
malformed timestamps, messy casing) so the validation layer has real work to do.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .config import Config

FIRST = ["Aarav", "Simran", "Harpreet", "Rohan", "Ananya", "Gurleen", "Kabir", "Isha", "Arjun", "Navneet",
         "Priya", "Manpreet", "Vikram", "Sana", "Jaspreet", "Neha", "Karan", "Tanvi", "Aditya", "Meera"]
LAST = ["Sharma", "Singh", "Kaur", "Verma", "Gill", "Mehta", "Sandhu", "Gupta", "Bedi", "Malhotra",
        "Chopra", "Dhillon", "Saini", "Bansal", "Arora"]
CITIES = ["Ludhiana", "Amritsar", "Jalandhar", "Patiala", "Mohali", "Chandigarh", "Delhi", "Jaipur",
          "Hoshiarpur", "Panchkula", "Mumbai", "Bengaluru"]
CATEGORIES = {
    "Electronics": (1500, 45000),
    "Home & Kitchen": (300, 9000),
    "Fashion": (400, 6000),
    "Books": (150, 1200),
    "Sports": (500, 12000),
    "Beauty": (200, 3500),
}
CHANNELS = ["web", "mobile_app", "marketplace", "store"]
STATUSES = ["completed", "completed", "completed", "completed", "returned", "cancelled"]


def _start(cfg: Config) -> date:
    return datetime.strptime(cfg.start_date, "%Y-%m-%d").date()


def generate_customers(cfg: Config) -> pd.DataFrame:
    rng = np.random.default_rng(cfg.seed)
    n = cfg.customers
    first = rng.choice(FIRST, n)
    last = rng.choice(LAST, n)
    ids = [f"C{i:05d}" for i in range(1, n + 1)]
    signup = [_start(cfg) - timedelta(days=int(d)) for d in rng.integers(0, 900, n)]
    return pd.DataFrame({
        "customer_id": ids,
        "full_name": [f"{a} {b}" for a, b in zip(first, last)],
        "email": [f"{a.lower()}.{b.lower()}{i}@example.com" for i, (a, b) in enumerate(zip(first, last))],
        "city": rng.choice(CITIES, n),
        "segment": rng.choice(["consumer", "consumer", "consumer", "small_business", "corporate"], n),
        "signup_date": [d.isoformat() for d in signup],
    })


def generate_products(cfg: Config) -> list[dict]:
    rng = np.random.default_rng(cfg.seed + 1)
    cats = list(CATEGORIES)
    out = []
    for i in range(1, cfg.products + 1):
        cat = cats[i % len(cats)]
        lo, hi = CATEGORIES[cat]
        out.append({
            "product_id": f"P{i:04d}",
            "name": f"{cat.split()[0]} Item {i:03d}",
            "category": cat,
            "unit_price_inr": round(float(rng.uniform(lo, hi)), 2),
            "active": bool(rng.random() > 0.03),
        })
    return out


def generate_orders_for_day(cfg: Config, day_index: int, products: list[dict]) -> pd.DataFrame:
    rng = np.random.default_rng(cfg.seed + 1000 + day_index)
    day = _start(cfg) + timedelta(days=day_index)
    # weekly seasonality + gentle upward trend + noise
    weekday_boost = 1.25 if day.weekday() >= 5 else 1.0
    n = max(10, int(cfg.orders_per_day * weekday_boost * (1 + day_index / 400) * rng.uniform(0.85, 1.15)))

    prod_idx = rng.integers(0, len(products), n)
    currency = rng.choice(["INR", "INR", "INR", "INR", "USD", "EUR"], n)
    fx = {k: v for k, v in cfg.fx_to_inr.items()}
    base_price = np.array([products[i]["unit_price_inr"] for i in prod_idx])
    unit_price = np.round(base_price / np.array([fx[c] for c in currency]) * rng.uniform(0.9, 1.05, n), 2)
    seconds = rng.integers(0, 86400, n)
    df = pd.DataFrame({
        "order_id": [f"O{day.strftime('%Y%m%d')}-{i:05d}" for i in range(n)],
        "order_ts": [(datetime.combine(day, datetime.min.time()) + timedelta(seconds=int(s))).isoformat()
                     for s in seconds],
        "customer_id": [f"C{int(c):05d}" for c in rng.integers(1, cfg.customers + 1, n)],
        "product_id": [products[i]["product_id"] for i in prod_idx],
        "quantity": rng.choice([1, 1, 1, 2, 2, 3, 4], n),
        "unit_price": unit_price,
        "currency": currency,
        "status": rng.choice(STATUSES, n),
        "channel": rng.choice(CHANNELS, n),
    })
    return _corrupt(df, rng, cfg.dirty_rate)


def _corrupt(df: pd.DataFrame, rng: np.random.Generator, rate: float) -> pd.DataFrame:
    df = df.copy()
    df["quantity"] = df["quantity"].astype(object)
    df["order_ts"] = df["order_ts"].astype(object)
    df["customer_id"] = df["customer_id"].astype(object)
    n = len(df)
    k = max(1, int(n * rate))
    rows = rng.choice(n, size=min(n, k), replace=False)
    kinds = ["neg_qty", "null_customer", "unknown_product", "bad_ts", "messy_status", "bad_currency"]
    for r in rows:
        kind = kinds[int(rng.integers(0, len(kinds)))]
        if kind == "neg_qty":
            df.at[r, "quantity"] = -int(rng.integers(1, 3))
        elif kind == "null_customer":
            df.at[r, "customer_id"] = None
        elif kind == "unknown_product":
            df.at[r, "product_id"] = "P9999"
        elif kind == "bad_ts":
            df.at[r, "order_ts"] = "not-a-timestamp"
        elif kind == "messy_status":  # recoverable: should be cleaned, not rejected
            df.at[r, "status"] = f"  {str(df.at[r, 'status']).upper()} "
        elif kind == "bad_currency":
            df.at[r, "currency"] = "XYZ"
    # duplicate deliveries from the order service (at-least-once semantics)
    dups = df.sample(n=max(1, k // 3), random_state=int(rng.integers(0, 1_000_000)))
    return pd.concat([df, dups], ignore_index=True)


def generate(cfg: Config, days: int) -> dict:
    cfg.orders_dir.mkdir(parents=True, exist_ok=True)
    customers_path = cfg.raw_dir / "customers.csv"
    products_path = cfg.raw_dir / "products.json"
    if not customers_path.exists():
        generate_customers(cfg).to_csv(customers_path, index=False)
    products = generate_products(cfg)
    if not products_path.exists():
        products_path.write_text(json.dumps(products, indent=2))
    written = 0
    for d in range(days):
        day = _start(cfg) + timedelta(days=d)
        path = cfg.orders_dir / f"orders_{day.isoformat()}.csv"
        if path.exists():
            continue
        generate_orders_for_day(cfg, d, products).to_csv(path, index=False)
        written += 1
    return {"order_files_written": written, "order_files_total": len(list(cfg.orders_dir.glob("orders_*.csv")))}


def order_file_date(path: Path) -> str:
    return path.stem.replace("orders_", "")
