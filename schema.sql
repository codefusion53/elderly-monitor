-- =====================================================================
-- Elderly Monitoring System - full database schema
-- PostgreSQL
--
-- This file runs automatically ONCE, when the database volume is first
-- created (via /docker-entrypoint-initdb.d). It is NOT re-run on an existing
-- database. For schema CHANGES to an existing database, use ALTER statements
-- (see the "Migrations" note at the end of this file and the README).
--
-- Sections:
--   1. Core (collector): residences, devices, readings, connectivity_events
--   2. Phase 3 (web/inference settings): residence_settings, users, sessions
--   3. Phase 3 (alerting): alert_contacts, alert_state, alert_log
--   4. Seed data
-- =====================================================================


-- =====================================================================
-- 1. CORE (collector)
-- =====================================================================

CREATE TABLE IF NOT EXISTS residences (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    timezone    TEXT NOT NULL DEFAULT 'Europe/Lisbon',  -- critical for "morning routine" logic
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS devices (
    id                  SERIAL PRIMARY KEY,
    tuya_device_id      TEXT NOT NULL UNIQUE,
    residence_id        INTEGER NOT NULL REFERENCES residences(id),
    name                TEXT NOT NULL,
    room                TEXT,
    -- 'peak'       = short high-power bursts signal human action (kettle, coffee maker, microwave)
    -- 'continuous' = long steady draw signals presence (TV, lamp)
    signal_type         TEXT NOT NULL DEFAULT 'peak',
    -- live connectivity state machine: 'online' | 'offline_suspected' | 'offline_confirmed' | 'unknown'
    conn_state          TEXT NOT NULL DEFAULT 'unknown',
    conn_state_since    TIMESTAMPTZ,
    last_successful_poll TIMESTAMPTZ,
    total_ele_wh        NUMERIC NOT NULL DEFAULT 0,  -- accumulated from add_ele increments
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Append-only raw telemetry. One row per successful poll per device.
CREATE TABLE IF NOT EXISTS readings (
    id              BIGSERIAL PRIMARY KEY,
    device_id       INTEGER NOT NULL REFERENCES devices(id),
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    cur_power_w     NUMERIC,      -- converted: Tuya sends tenths of a watt
    cur_current_ma  NUMERIC,
    cur_voltage_v   NUMERIC,      -- converted: Tuya sends tenths of a volt
    add_ele_raw     NUMERIC,      -- raw increment as reported this poll
    switch_on       BOOLEAN,
    online          BOOLEAN
);
CREATE INDEX IF NOT EXISTS idx_readings_device_ts ON readings (device_id, ts DESC);

-- Every confirmed transition online <-> offline. This table IS the
-- "no data is never no activity" deliverable.
CREATE TABLE IF NOT EXISTS connectivity_events (
    id          BIGSERIAL PRIMARY KEY,
    device_id   INTEGER NOT NULL REFERENCES devices(id),
    event_type  TEXT NOT NULL,          -- 'offline_confirmed' | 'back_online'
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    detail      TEXT
);
CREATE INDEX IF NOT EXISTS idx_conn_events_device_ts ON connectivity_events (device_id, ts DESC);


-- =====================================================================
-- 2. PHASE 3 - settings, users, sessions
-- =====================================================================

-- Per-residence tunable inference/alert settings (admin-adjustable).
CREATE TABLE IF NOT EXISTS residence_settings (
    residence_id            INTEGER PRIMARY KEY REFERENCES residences(id),
    -- fraction of the learned ceiling at which we escalate GREEN -> YELLOW
    yellow_fraction         NUMERIC NOT NULL DEFAULT 0.75,
    -- minutes without a successful poll before a plug is offline_confirmed
    offline_tolerance_min   INTEGER NOT NULL DEFAULT 20,
    -- minutes after which live data is considered stale (system health)
    stale_after_min         INTEGER NOT NULL DEFAULT 10,
    -- optional manual override of the deviation ceiling (NULL = use learned)
    ceiling_override_min    INTEGER,
    -- alert escalation thresholds (minutes)
    extended_offline_min        INTEGER NOT NULL DEFAULT 180,  -- single plug offline -> critical
    total_offline_critical_min  INTEGER NOT NULL DEFAULT 40,   -- all plugs offline -> critical
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Users with roles. A caregiver is scoped to one residence; an admin
-- manages everything.
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'caregiver',   -- 'admin' | 'caregiver'
    residence_id    INTEGER REFERENCES residences(id),   -- NULL for admin
    display_name    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Server-side sessions (simple, revocable).
CREATE TABLE IF NOT EXISTS sessions (
    token       TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id);


-- =====================================================================
-- 3. PHASE 3 - alerting
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


-- =====================================================================
-- 4. SEED DATA (test residence + the two known plugs; settings row)
-- =====================================================================

INSERT INTO residences (name, timezone)
SELECT 'Casa de teste (Abdulo)', 'Europe/Lisbon'
WHERE NOT EXISTS (SELECT 1 FROM residences);

INSERT INTO devices (tuya_device_id, residence_id, name, room, signal_type)
VALUES
    ('bf859ac78e5a1eb647ivgh', 1, 'Cafeteira cozinha', 'Cozinha', 'peak'),
    ('bff60a8e5d09c97722owqd', 1, 'Abajur de quarto',  'Quarto',  'continuous')
ON CONFLICT (tuya_device_id) DO NOTHING;

-- default settings row for every residence
INSERT INTO residence_settings (residence_id)
SELECT id FROM residences
ON CONFLICT (residence_id) DO NOTHING;


-- =====================================================================
-- MIGRATIONS (for EXISTING databases only)
-- The CREATE statements above only run on a fresh volume. To bring an
-- already-initialized database up to date, these ALTERs are idempotent and
-- safe to re-run:
--
--   ALTER TABLE residence_settings
--     ADD COLUMN IF NOT EXISTS extended_offline_min INTEGER NOT NULL DEFAULT 180,
--     ADD COLUMN IF NOT EXISTS total_offline_critical_min INTEGER NOT NULL DEFAULT 40;
--
-- (Run any future ALTERs the same way and record them here.)
-- =====================================================================
