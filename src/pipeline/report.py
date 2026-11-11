"""Render README images from the warehouse: everything shown is computed from real pipeline output."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

INK = "#0e1a2b"
MUTED = "#5b6676"
ACCENT = "#2747d6"
SIGNAL = "#c97d06"
GOOD = "#1f9d5c"
BAD = "#c6373a"
GRID = "#e3e7ee"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.edgecolor": GRID,
    "axes.labelcolor": MUTED,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.titleweight": "bold",
    "axes.titlesize": 13,
    "axes.titlecolor": INK,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 150,
})


def _inr(x: float, _pos=None) -> str:
    if x >= 1e7:
        return f"₹{x / 1e7:.1f} Cr"
    if x >= 1e5:
        return f"₹{x / 1e5:.1f} L"
    return f"₹{x:,.0f}"


def daily_revenue(con: sqlite3.Connection, out: Path) -> None:
    df = pd.read_sql("SELECT * FROM mart_daily_revenue", con, parse_dates=["date"])
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(df["date"], df["revenue_inr"], color=[SIGNAL if w else "#c9d2e3" for w in df["is_weekend"]],
           width=0.8, label="Daily revenue (weekend highlighted)")
    ax.plot(df["date"], df["revenue_inr"].rolling(7, min_periods=1).mean(), color=ACCENT, lw=2.2,
            label="7-day moving average")
    ax.yaxis.set_major_formatter(_inr)
    ax.grid(axis="y", color=GRID)
    ax.set_title("Recognised revenue per day")
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(out / "daily_revenue.png")
    plt.close(fig)


def category_revenue(con: sqlite3.Connection, out: Path) -> None:
    df = pd.read_sql("SELECT * FROM mart_category_revenue", con).sort_values("revenue_inr")
    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.barh(df["category"], df["revenue_inr"], color=ACCENT)
    for b, rr in zip(bars, df["return_rate"]):
        ax.text(b.get_width(), b.get_y() + b.get_height() / 2, f"  {_inr(b.get_width())} · {rr:.1%} returned",
                va="center", fontsize=8.5, color=MUTED)
    ax.xaxis.set_major_formatter(_inr)
    ax.set_xlim(0, df["revenue_inr"].max() * 1.45)
    ax.grid(axis="x", color=GRID)
    ax.set_title("Revenue by category")
    fig.tight_layout()
    fig.savefig(out / "category_revenue.png")
    plt.close(fig)


def rejects_breakdown(con: sqlite3.Connection, out: Path) -> None:
    df = pd.read_sql("SELECT reject_reason, COUNT(*) AS n FROM rejected_orders GROUP BY 1 ORDER BY n", con)
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.barh(df["reject_reason"], df["n"], color=BAD)
    for i, n in enumerate(df["n"]):
        ax.text(n, i, f" {n}", va="center", fontsize=9, color=MUTED)
    ax.grid(axis="x", color=GRID)
    ax.set_title("Rows quarantined by validation rule")
    ax.set_xlabel("rows")
    fig.tight_layout()
    fig.savefig(out / "rejects_by_reason.png")
    plt.close(fig)


def run_history(con: sqlite3.Connection, out: Path) -> None:
    runs = pd.read_sql("SELECT run_id, status, files, rows_in, rows_loaded, rows_rejected FROM etl_runs "
                       "ORDER BY run_id", con)
    checks = pd.read_sql("SELECT run_id, check_name, passed, observed, expected FROM dq_results "
                         "WHERE run_id = (SELECT MAX(run_id) FROM dq_results)", con)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 3.8), gridspec_kw={"width_ratios": [1.05, 1]})
    for ax in (a1, a2):
        ax.axis("off")
    a1.set_title("ETL run log (etl_runs)", loc="left")
    t1 = a1.table(cellText=runs.values, colLabels=[c.replace("_", " ") for c in runs.columns],
                  loc="upper left", cellLoc="center")
    a2.set_title(f"Data quality checks, run {int(checks['run_id'].iloc[0]) if len(checks) else '-'}", loc="left")
    shown = checks.assign(result=checks["passed"].map({1: "PASS", 0: "FAIL"}))[
        ["check_name", "observed", "expected", "result"]]
    t2 = a2.table(cellText=shown.values, colLabels=["check", "observed", "expected", "result"],
                  loc="upper left", cellLoc="left", colWidths=[0.36, 0.3, 0.18, 0.16])
    for t in (t1, t2):
        t.auto_set_font_size(False)
        t.set_fontsize(8.5)
        t.scale(1, 1.35)
        for (r, c), cell in t.get_celld().items():
            cell.set_edgecolor(GRID)
            if r == 0:
                cell.set_text_props(weight="bold", color=INK)
                cell.set_facecolor("#f1f4f8")
    for (r, c), cell in t1.get_celld().items():
        if r > 0 and c == 1:
            s = cell.get_text().get_text()
            cell.get_text().set_color(GOOD if s == "success" else (BAD if s == "failed" else MUTED))
    for (r, c), cell in t2.get_celld().items():
        if r > 0 and c == 3:
            cell.get_text().set_color(GOOD if cell.get_text().get_text() == "PASS" else BAD)
            cell.get_text().set_weight("bold")
    fig.tight_layout()
    fig.savefig(out / "run_log_and_quality.png")
    plt.close(fig)


def architecture(out: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 4.2))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 4.2)
    ax.axis("off")

    def box(x, y, w, h, title, sub, color=INK, fill="white"):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                                    lw=1.6, edgecolor=color, facecolor=fill))
        ax.text(x + w / 2, y + h * 0.64, title, ha="center", va="center", fontsize=10.5, weight="bold",
                color=color)
        ax.text(x + w / 2, y + h * 0.3, sub, ha="center", va="center", fontsize=8, color=MUTED)

    def arrow(x1, y1, x2, y2):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=14, lw=1.4,
                                     color=MUTED))

    box(0.2, 2.75, 2.1, 1.0, "Order service", "daily CSV drops")
    box(0.2, 1.6, 2.1, 1.0, "CRM export", "customers.csv")
    box(0.2, 0.45, 2.1, 1.0, "Catalogue API", "products.json")
    box(3.1, 1.6, 2.0, 1.0, "Extract", "new files only\n(processed_files)")
    box(5.8, 1.6, 2.0, 1.0, "Transform", "clean · dedupe · FX→INR")
    box(5.8, 0.25, 2.0, 0.95, "Quarantine", "rejected_orders", color=BAD)
    box(8.5, 1.6, 1.6, 1.0, "Validate", "8 DQ checks", color=SIGNAL)
    box(10.4, 2.6, 1.45, 1.25, "Warehouse", "star schema\n+ marts", color=ACCENT)
    box(10.4, 0.6, 1.45, 1.25, "Reports", "charts in\ndocs/images")

    for y in (3.25, 2.1, 0.95):
        arrow(2.3, y, 3.1, 2.1)
    arrow(5.1, 2.1, 5.8, 2.1)
    arrow(6.8, 1.6, 6.8, 1.2)
    arrow(7.8, 2.1, 8.5, 2.1)
    arrow(10.1, 2.3, 10.4, 3.0)
    arrow(11.125, 2.6, 11.125, 1.85)
    ax.text(9.3, 1.2, "fail → run aborted,\nnothing committed", ha="center", fontsize=7.5, color=BAD)
    ax.set_title("retail-sales-data-pipeline: one transaction per run", loc="left")
    fig.tight_layout()
    fig.savefig(out / "architecture.png")
    plt.close(fig)


def render_all(warehouse: Path, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    architecture(out)
    con = sqlite3.connect(warehouse)
    try:
        daily_revenue(con, out)
        category_revenue(con, out)
        rejects_breakdown(con, out)
        run_history(con, out)
    finally:
        con.close()
    return sorted(out.glob("*.png"))
