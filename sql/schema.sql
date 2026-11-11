-- Star schema for the sales warehouse (SQLite dialect; portable to PostgreSQL with minor type changes).

CREATE TABLE IF NOT EXISTS dim_date (
    date_key     INTEGER PRIMARY KEY,   -- yyyymmdd
    date         TEXT    NOT NULL,
    year         INTEGER NOT NULL,
    quarter      INTEGER NOT NULL,
    month        INTEGER NOT NULL,
    month_name   TEXT    NOT NULL,
    iso_week     INTEGER NOT NULL,
    day_of_week  INTEGER NOT NULL,      -- 1 = Monday
    is_weekend   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_customer (
    customer_id  TEXT PRIMARY KEY,
    full_name    TEXT NOT NULL,
    email        TEXT,
    city         TEXT,
    segment      TEXT,
    signup_date  TEXT
);

CREATE TABLE IF NOT EXISTS dim_product (
    product_id      TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    category        TEXT NOT NULL,
    unit_price_inr  REAL NOT NULL,
    active          INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_sales (
    order_id     TEXT PRIMARY KEY,
    order_ts     TEXT    NOT NULL,
    date_key     INTEGER NOT NULL REFERENCES dim_date(date_key),
    customer_id  TEXT    NOT NULL REFERENCES dim_customer(customer_id),
    product_id   TEXT    NOT NULL REFERENCES dim_product(product_id),
    quantity     INTEGER NOT NULL CHECK (quantity > 0),
    unit_price   REAL    NOT NULL,
    currency     TEXT    NOT NULL,
    fx_rate      REAL    NOT NULL,
    amount_inr   REAL    NOT NULL,
    revenue_inr  REAL    NOT NULL,
    status       TEXT    NOT NULL,
    channel      TEXT    NOT NULL,
    source_file  TEXT    NOT NULL,
    loaded_run   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_fact_sales_date ON fact_sales(date_key);
CREATE INDEX IF NOT EXISTS ix_fact_sales_product ON fact_sales(product_id);

-- Rows that failed validation, kept for triage instead of being dropped.
CREATE TABLE IF NOT EXISTS rejected_orders (
    run_id        INTEGER NOT NULL,
    source_file   TEXT    NOT NULL,
    order_id      TEXT,
    reject_reason TEXT    NOT NULL,
    raw_record    TEXT    NOT NULL
);

-- One row per pipeline run: the audit trail.
CREATE TABLE IF NOT EXISTS etl_runs (
    run_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at     TEXT NOT NULL,
    finished_at    TEXT,
    status         TEXT NOT NULL,       -- running | success | failed | no_new_data
    files          INTEGER DEFAULT 0,
    rows_in        INTEGER DEFAULT 0,
    rows_loaded    INTEGER DEFAULT 0,
    rows_rejected  INTEGER DEFAULT 0,
    message        TEXT
);

CREATE TABLE IF NOT EXISTS dq_results (
    run_id    INTEGER NOT NULL,
    check_name TEXT   NOT NULL,
    passed    INTEGER NOT NULL,
    observed  TEXT,
    expected  TEXT,
    severity  TEXT
);

-- Incremental-load bookkeeping: which source files have been committed.
CREATE TABLE IF NOT EXISTS processed_files (
    source_file  TEXT PRIMARY KEY,
    file_date    TEXT NOT NULL,
    run_id       INTEGER NOT NULL
);
