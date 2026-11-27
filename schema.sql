-- Optional PostgreSQL schema for persisting runs. The MVP does not require a database.
-- Store only what the app needs; avoid names, PAN, or contact details.

CREATE TABLE fund (
    scheme_code     INTEGER PRIMARY KEY,
    scheme_name     TEXT NOT NULL,
    category        TEXT,
    plan_type       TEXT,              -- e.g. Direct / Regular
    expense_ratio   NUMERIC(5,4),      -- fraction, 0.0105 = 1.05%
    top10_holdings  NUMERIC(5,4),
    metadata_as_of  DATE
);

CREATE TABLE nav_history (
    scheme_code INTEGER REFERENCES fund(scheme_code),
    nav_date    DATE NOT NULL,
    nav         NUMERIC(14,4) NOT NULL CHECK (nav > 0),
    source      TEXT NOT NULL,
    PRIMARY KEY (scheme_code, nav_date)
);

CREATE TABLE risk_assessment (
    id               BIGSERIAL PRIMARY KEY,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    anon_session_id  UUID NOT NULL,    -- random id, not linked to a person
    capacity         NUMERIC(5,2),
    tolerance        NUMERIC(5,2),
    required         NUMERIC(5,2),
    bearable         NUMERIC(5,2),
    profile          TEXT NOT NULL,
    required_return  NUMERIC(6,4),
    warnings         JSONB
);

CREATE TABLE fund_metric_snapshot (
    scheme_code  INTEGER REFERENCES fund(scheme_code),
    as_of        DATE NOT NULL,
    window_years NUMERIC(4,1) NOT NULL,
    cagr NUMERIC(8,5), volatility NUMERIC(8,5), sharpe NUMERIC(8,4),
    max_drawdown NUMERIC(8,5), beta NUMERIC(8,4),
    PRIMARY KEY (scheme_code, as_of, window_years)
);
