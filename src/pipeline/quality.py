"""Data quality checks run on every batch before it is committed."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass
class CheckResult:
    name: str
    passed: bool
    observed: str
    expected: str
    severity: str = "error"  # "error" blocks the load, "warn" is reported only

    def to_dict(self) -> dict:
        return asdict(self)


def run_checks(
    clean: pd.DataFrame,
    rejects: pd.DataFrame,
    dim_customer: pd.DataFrame,
    dim_product: pd.DataFrame,
    *,
    max_reject_rate: float,
    max_null_rate: float,
    min_rows: int,
) -> list[CheckResult]:
    total_in = len(clean) + len(rejects)
    results: list[CheckResult] = []

    results.append(CheckResult(
        "row_count", len(clean) >= min_rows, f"{len(clean)} rows", f">= {min_rows}"))

    reject_rate = (len(rejects) / total_in) if total_in else 0.0
    results.append(CheckResult(
        "reject_rate", reject_rate <= max_reject_rate, f"{reject_rate:.2%}", f"<= {max_reject_rate:.0%}"))

    required = ["order_id", "order_ts", "customer_id", "product_id", "quantity", "amount_inr"]
    null_rate = float(clean[required].isna().mean().max()) if len(clean) else 0.0
    results.append(CheckResult(
        "required_not_null", null_rate <= max_null_rate, f"max {null_rate:.2%}", f"<= {max_null_rate:.0%}"))

    dup = int(clean["order_id"].duplicated().sum())
    results.append(CheckResult("order_id_unique", dup == 0, f"{dup} duplicates", "0"))

    orphans_c = int((~clean["customer_id"].isin(dim_customer["customer_id"])).sum())
    results.append(CheckResult("fk_customer", orphans_c == 0, f"{orphans_c} orphans", "0"))

    orphans_p = int((~clean["product_id"].isin(dim_product["product_id"])).sum())
    results.append(CheckResult("fk_product", orphans_p == 0, f"{orphans_p} orphans", "0"))

    neg = int((clean["amount_inr"] < 0).sum())
    results.append(CheckResult("amount_not_negative", neg == 0, f"{neg} negative", "0"))

    if len(clean):
        median = clean["amount_inr"].median()
        outliers = int((clean["amount_inr"] > median * 50).sum())
        results.append(CheckResult(
            "amount_outliers", outliers == 0, f"{outliers} > 50x median", "0", severity="warn"))

    return results


def blocking_failures(results: list[CheckResult]) -> list[CheckResult]:
    return [r for r in results if not r.passed and r.severity == "error"]
