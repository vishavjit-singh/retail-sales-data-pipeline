import pandas as pd

from pipeline.transform import build_dim_date, clean_orders

FX = {"INR": 1.0, "USD": 83.0}
PRODUCTS = pd.DataFrame({"product_id": ["P1", "P2"]})
CUSTOMERS = pd.DataFrame({"customer_id": ["C1", "C2"]})


def orders(**overrides):
    row = {"order_id": "O1", "order_ts": "2026-01-05T10:00:00", "customer_id": "C1", "product_id": "P1",
           "quantity": "2", "unit_price": "100", "currency": "INR", "status": "completed", "channel": "web"}
    row.update(overrides)
    return row


def test_duplicates_are_collapsed_not_rejected():
    df = pd.DataFrame([orders(), orders()])
    clean, rejects = clean_orders(df, PRODUCTS, CUSTOMERS, FX)
    assert len(clean) == 1 and len(rejects) == 0


def test_messy_status_is_repaired():
    clean, rejects = clean_orders(pd.DataFrame([orders(status="  COMPLETED ")]), PRODUCTS, CUSTOMERS, FX)
    assert clean.loc[0, "status"] == "completed" and rejects.empty


def test_fx_conversion_and_revenue_recognition():
    df = pd.DataFrame([orders(order_id="A", currency="USD", unit_price="10"),
                       orders(order_id="B", status="returned")])
    clean, _ = clean_orders(df, PRODUCTS, CUSTOMERS, FX)
    clean = clean.set_index("order_id")
    assert clean.loc["A", "amount_inr"] == 2 * 10 * 83.0
    assert clean.loc["A", "revenue_inr"] == clean.loc["A", "amount_inr"]
    assert clean.loc["B", "revenue_inr"] == 0.0  # returns carry no revenue


def test_each_bad_row_gets_one_reason():
    df = pd.DataFrame([
        orders(order_id="ts", order_ts="not-a-timestamp"),
        orders(order_id="nc", customer_id=None),
        orders(order_id="uc", customer_id="C999"),
        orders(order_id="up", product_id="P999"),
        orders(order_id="nq", quantity="-1"),
        orders(order_id="cur", currency="XYZ"),
        orders(order_id="ok"),
    ])
    clean, rejects = clean_orders(df, PRODUCTS, CUSTOMERS, FX)
    assert list(clean["order_id"]) == ["ok"]
    assert dict(zip(rejects["order_id"], rejects["reject_reason"])) == {
        "ts": "invalid_timestamp", "nc": "missing_customer", "uc": "unknown_customer",
        "up": "unknown_product", "nq": "non_positive_quantity", "cur": "unsupported_currency"}


def test_dim_date_flags_weekends():
    dim = build_dim_date(pd.Series([20260103, 20260105]))  # Sat, Mon
    assert dim.set_index("date_key")["is_weekend"].to_dict() == {20260103: 1, 20260105: 0}
