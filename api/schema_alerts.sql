-- =====================================================================
-- Phase 3 alerting schema. Apply once.
-- =====================================================================

-- Where and how to notify, per residence. Multiple contacts allowed.
CREATE TABLE IF NOT EXISTS alert_contacts (
    id            SERIAL PRIMARY KEY,
    residence_id  INTEGER NOT NULL REFERENCES residences(id),
    name          TEXT,
    email         TEXT,
    whatsapp      TEXT,            -- E.164 phone, e.g. +351912345678
    -- which tiers this contact receives: 'all' | 'critical'
    tier          TEXT NOT NULL DEFAULT 'all',
    active         BOOLEAN NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Remembers the last notified state per residence, so we alert on CHANGE
-- and never spam the same state every cycle.
CREATE TABLE IF NOT EXISTS alert_state (
    residence_id     INTEGER PRIMARY KEY REFERENCES residences(id),
    last_state       TEXT,          -- GREEN | YELLOW | RED | SYSTEM
    last_category    TEXT,          -- activity | system
    last_changed_at  TIMESTAMPTZ,
    last_notified_at TIMESTAMPTZ
);

-- Audit log of every notification actually sent (for the admin + debugging).
CREATE TABLE IF NOT EXISTS alert_log (
    id            BIGSERIAL PRIMARY KEY,
    residence_id  INTEGER NOT NULL REFERENCES residences(id),
    ts            TIMESTAMPTZ NOT NULL DEFAULT now(),
    channel       TEXT,             -- email | whatsapp
    to_addr       TEXT,
    tier          TEXT,             -- routine | critical
    state         TEXT,
    subject       TEXT,
    ok            BOOLEAN,
    detail        TEXT
);
CREATE INDEX IF NOT EXISTS idx_alert_log_res_ts ON alert_log (residence_id, ts DESC);
