-- =====================================================================
-- Elderly Monitoring System
-- PostgreSQL
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
-- Seed: Abdulo's test residence and the two known plugs
-- =====================================================================
INSERT INTO residences (name, timezone)
SELECT 'Casa de teste (Abdulo)', 'Europe/Lisbon'
WHERE NOT EXISTS (SELECT 1 FROM residences);

INSERT INTO devices (tuya_device_id, residence_id, name, room, signal_type)
VALUES
    ('bf859ac78e5a1eb647ivgh', 1, 'Cafeteira cozinha', 'Cozinha', 'peak'),
    ('bff60a8e5d09c97722owqd', 1, 'Abajur de quarto',  'Quarto',  'continuous')
ON CONFLICT (tuya_device_id) DO NOTHING;
