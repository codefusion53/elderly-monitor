-- =====================================================================
-- Phase 3 schema additions: users, roles, per-residence settings.
-- Apply once against the existing database.
-- =====================================================================

-- Per-residence tunable inference/alert settings (admin-adjustable).
-- One row per residence; created with sensible defaults.
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

-- Seed default settings for every existing residence.
INSERT INTO residence_settings (residence_id)
SELECT id FROM residences
ON CONFLICT (residence_id) DO NOTHING;

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
