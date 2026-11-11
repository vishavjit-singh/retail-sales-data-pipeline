import pandas as pd

from pipeline.quality import blocking_failures, run_checks

DIM_C = pd.DataFrame({"customer_id": ["C1"]})
DIM_P = pd.DataFrame({"product_id": ["P1"]})


def fact(**kw):
    row = {"order_id": "O1", "order_ts": pd.Timestamp("2026-01-01"), "customer_id": "C1", "product_id": "P1",
           "quantity": 1, "amount_inr": 100.0}
    row.update(kw)
    return pd.DataFrame([row])


def check(clean, rejects=None, **kw):
    params = dict(max_reject_rate=0.1, max_null_rate=0.0, min_rows=1) | kw
    return run_checks(clean, rejects if rejects is not None else pd.DataFrame(), DIM_C, DIM_P, **params)


def test_clean_batch_passes():
    assert blocking_failures(check(fact())) == []


def test_orphan_product_blocks_load():
    names = [r.name for r in blocking_failures(check(fact(product_id="P404")))]
    assert names == ["fk_product"]


def test_high_reject_rate_blocks_load():
    rejects = pd.DataFrame({"order_id": ["x", "y"]})
    names = [r.name for r in blocking_failures(check(fact(), rejects))]
    assert "reject_rate" in names


def test_outliers_only_warn():
    clean = pd.concat([fact(order_id=f"O{i}") for i in range(5)] + [fact(order_id="big", amount_inr=1e9)])
    results = check(clean)
    assert blocking_failures(results) == []
    assert next(r for r in results if r.name == "amount_outliers").passed is False
