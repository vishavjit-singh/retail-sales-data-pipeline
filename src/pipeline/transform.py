"""Cleaning, validation and dimensional modelling."""
from __future__ import annotations

import pandas as pd

VALID_STATUS = {"completed", "returned", "cancelled"}


def clean_orders(
    orders: pd.DataFrame,
    products: pd.DataFrame,
    customers: pd.DataFrame,
    fx_to_inr: dict[str, float],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (clean_orders, rejected_rows).

    Recoverable issues (whitespace, casing, exact duplicates) are fixed.
    Unrecoverable issues are moved to the rejects table with a reason so
    nothing is silently dropped.
    """
    df = orders.copy()
    df["status"] = df["status"].astype(str).str.strip().str.lower()
    df["currency"] = df["currency"].astype(str).str.strip().str.upper()
    df["channel"] = df["channel"].astype(str).str.strip().str.lower()

    # at-least-once delivery from the source: keep the first copy of each order_id
    df = df.drop_duplicates(subset="order_id", keep="first")

    df["order_ts_parsed"] = pd.to_datetime(df["order_ts"], errors="coerce", format="ISO8601")
    df["quantity_num"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["unit_price_num"] = pd.to_numeric(df["unit_price"], errors="coerce")

    known_products = set(products["product_id"])
    known_customers = set(customers["customer_id"])

    reasons = pd.Series("", index=df.index, dtype=object)

    def flag(mask: pd.Series, reason: str) -> None:
        empty = reasons == ""
        reasons.loc[mask & empty] = reason

    flag(df["order_ts_parsed"].isna(), "invalid_timestamp")
    flag(df["customer_id"].isna() | (df["customer_id"].astype(str).str.strip() == ""), "missing_customer")
    flag(~df["customer_id"].isin(known_customers) & df["customer_id"].notna(), "unknown_customer")
    flag(~df["product_id"].isin(known_products), "unknown_product")
    flag(df["quantity_num"].isna() | (df["quantity_num"] <= 0), "non_positive_quantity")
    flag(df["unit_price_num"].isna() | (df["unit_price_num"] <= 0), "non_positive_price")
    flag(~df["currency"].isin(fx_to_inr.keys()), "unsupported_currency")
    flag(~df["status"].isin(VALID_STATUS), "invalid_status")

    bad = reasons != ""
    rejects = orders.loc[df.index[bad]].copy()
    rejects["reject_reason"] = reasons[bad].values

    good = df.loc[~bad].copy()
    good["order_ts"] = good["order_ts_parsed"]
    good["quantity"] = good["quantity_num"].astype(int)
    good["unit_price"] = good["unit_price_num"].astype(float)
    good["fx_rate"] = good["currency"].map(fx_to_inr).astype(float)
    good["amount_inr"] = (good["quantity"] * good["unit_price"] * good["fx_rate"]).round(2)
    # returned and cancelled orders carry no recognised revenue
    good["revenue_inr"] = good["amount_inr"].where(good["status"] == "completed", 0.0)
    good["date_key"] = good["order_ts"].dt.strftime("%Y%m%d").astype(int)
    cols = ["order_id", "order_ts", "date_key", "customer_id", "product_id", "quantity", "unit_price",
            "currency", "fx_rate", "amount_inr", "revenue_inr", "status", "channel"]
    return good[cols].reset_index(drop=True), rejects.reset_index(drop=True)


def build_dim_date(date_keys: pd.Series) -> pd.DataFrame:
    dates = pd.to_datetime(pd.Series(sorted(set(date_keys))).astype(str), format="%Y%m%d")
    return pd.DataFrame({
        "date_key": dates.dt.strftime("%Y%m%d").astype(int),
        "date": dates.dt.strftime("%Y-%m-%d"),
        "year": dates.dt.year,
        "quarter": dates.dt.quarter,
        "month": dates.dt.month,
        "month_name": dates.dt.strftime("%b"),
        "iso_week": dates.dt.isocalendar().week.astype(int).values,
        "day_of_week": dates.dt.dayofweek + 1,
        "is_weekend": (dates.dt.dayofweek >= 5).astype(int),
    })


def build_dim_customer(customers: pd.DataFrame) -> pd.DataFrame:
    df = customers.copy()
    df["email"] = df["email"].str.strip().str.lower()
    df["city"] = df["city"].str.strip().str.title()
    return df[["customer_id", "full_name", "email", "city", "segment", "signup_date"]]


def build_dim_product(products: pd.DataFrame) -> pd.DataFrame:
    df = products.copy()
    df["active"] = df["active"].astype(int)
    return df[["product_id", "name", "category", "unit_price_inr", "active"]]
