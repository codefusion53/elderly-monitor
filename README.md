# Elderly Monitoring System

Non-intrusive monitoring of an elderly person's wellbeing, inferred from the
electricity consumption of Wi-Fi smart plugs (Tuya ecosystem). The system
learns each home's normal routine, flags significant deviations, shows a
live traffic-light dashboard, and notifies family when something is wrong.

One principle stays central throughout:

**"No data" is never confused with "no activity".** Every connectivity gap is
detected, bounded, and reported as a system event, kept completely separate
from any statement about the person.

## Subsystems

```
collector/   Reads the plugs via the Tuya Cloud API every 60s, stores raw
             telemetry, runs the connectivity state machine.
inference/   Learns the routine baseline and decides green/yellow/red (brain).
interface/   Read-only reporting/visualization: charts, shared DB access.
api/         FastAPI web layer: live state API, dashboard, login, two
             profiles (Family/Caregiver + Admin), sensitivity settings,
             and the alerting engine (email + WhatsApp).
```

```
Smart plugs -> Tuya Cloud API -> collector -> PostgreSQL
                                                 |
                        inference <-------------- +
                            |                     |
                           api (state) -----------+---- interface (charts)
                            |
                    dashboard + alerts -> family (email / WhatsApp)
```

## collector/

Polls each plug every `POLL_INTERVAL_SECONDS` (default 60), converts Tuya's
tenths-of-a-watt / tenths-of-a-volt values to real units, accumulates the
`add_ele` energy increment, and writes to `readings`, `devices`, and
`connectivity_events`.

Connectivity state machine:
```
unknown -> online -> offline_suspected -> offline_confirmed
             ^              |                    |
             +--------------+---- back_online ----+
```
A failed poll or `online=false` moves a device to `offline_suspected` and
nothing is emitted, so short Wi-Fi flickers trigger nothing. Only after
`OFFLINE_TOLERANCE_MINUTES` (default 20) does it become `offline_confirmed`,
writing a `connectivity_events` row. Recovery writes `back_online`.

Note: when a plug is offline, Tuya's `getstatus` may return cached values, so
the authoritative liveness signal is the `online` flag from the device-detail
endpoint, fetched every poll.

## inference/

- `baseline.py`: detects activity events (readings above a per-device wattage
  threshold, de-duplicated), learns per-hour activity probability, the typical
  and maximum gap between events, and habitual quiet hours. Data gaps are
  excluded from learning, so no-data is never learned as a quiet day.
  Low-signal devices (e.g. an LED lamp) are excluded from activity inference
  but still monitored for connectivity.
- `deviation.py`: green/yellow/red logic. GREEN = recent activity; YELLOW =
  silence approaching the ceiling; RED (activity) = silence past the ceiling
  during waking hours; RED (system) = offline, reported as a system fault
  distinct from inactivity. Accepts optional `yellow_fraction` and
  `ceiling_override_min` from the per-residence admin settings.
- `report.py`: validation runner; replays history day by day, classifying each
  day GREEN/YELLOW/RED/SEM DADOS. `python -m inference.report`.

## interface/

Read-only tooling. `data_access.py` is the shared DB layer. Chart generators
render the routine chart (learned routine + day-by-day state strip) and the
consumption curve.

## api/  (Phase 3 web layer)

FastAPI app serving the live system and the family/admin experience.

Run:
```
pip install fastapi uvicorn bcrypt
uvicorn api.app:app --host 127.0.0.1 --port 8000
```

Endpoints and pages:
- `GET /login` and `POST /api/login` / `GET /api/logout`: session auth.
- `GET /`: caregiver dashboard (semaforo, routine chips, data-freshness
  banner). Auto-refreshes every 60s.
- `GET /api/state`: JSON of per-device states + residence rollup + system
  health (requires login).
- `GET /admin` and `POST /api/settings/{residence_id}`: admin-only.
  Per-residence sensitivity controls (yellow fraction, offline tolerance,
  data-staleness window, optional manual silence ceiling), applied live.

Roles: `caregiver` (dashboard only), `admin` (dashboard + settings).

### System health / data freshness

If the newest reading is older than the residence's `stale_after_min`, the
dashboard shows a SYSTEM state ("Sistema sem dados") instead of presenting an
activity verdict computed from stale data. This is the "no data is never no
activity" principle enforced in the UI.

### Alerting (api/alerting.py, api/notify.py)

Stateful engine: each cycle it computes the current state, compares to the
last-notified state, and notifies only on CHANGE (never spams a stable state).

Tiering:
- routine (YELLOW, and return-to-GREEN): email to `all`-tier contacts.
- critical (RED activity, or SYSTEM/offline): WhatsApp + email to all contacts.

Channels (api/notify.py): email via SMTP (works immediately, free) and
WhatsApp via the Business API (Twilio-style; needs the client's Business
account). Both fail safely if unconfigured.

Run one cycle: `python -m api.alerting`
Run as a loop: `python -m api.alerting --loop 300` (or schedule with cron).

## check/

Diagnostics (read `.env`): `tuya_connection_test.py` (auth, device list, live
status) and `tuya_region_sweep.py` (locate/rule out mislocated credentials).

## Setup

1. `cp .env.example .env` and fill in real values, including `DB_PASSWORD`
   (used by docker-compose). `.env` is git-ignored and must never be committed.
2. `docker-compose up -d --build`.
3. Apply the Phase 3 schema:
   ```
   docker-compose exec -T db psql -U monitor -d monitor < api/schema_phase3.sql
   docker-compose exec -T db psql -U monitor -d monitor < api/schema_alerts.sql
   ```
4. Create an admin user:
   ```
   python -c "from api.auth import create_user; create_user('admin','PICK_A_PASSWORD',role='admin')"
   ```
5. Run the web app (see api/ above). The collector runs in Docker; the web app
   and alerting loop can run alongside it.

The collector retries the DB connection on startup (up to 30 attempts). A
wrong DB password fails immediately and loudly instead of retrying.

### .env keys

```
TUYA_REGION, TUYA_ACCESS_ID, TUYA_ACCESS_SECRET   # Tuya API
DB_PASSWORD, DATABASE_URL                          # database (same password)
POLL_INTERVAL_SECONDS, OFFLINE_TOLERANCE_MINUTES   # collector
SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM   # email alerts
WHATSAPP_API_URL, WHATSAPP_API_TOKEN, WHATSAPP_FROM    # WhatsApp alerts
```
`.env` values are read literally: no quotes, no trailing spaces.

## Security posture

- The database password lives only in `.env` (as `DB_PASSWORD`); it is not
  hardcoded in `docker-compose.yml`, which interpolates `${DB_PASSWORD}`.
- No public database exposure: Postgres is bound to `127.0.0.1` only. Verify
  with `ss -tlnp | grep 5432`; it must never show `0.0.0.0:5432`. Docker
  publishes ports past UFW, so the binding is the boundary.
- Passwords are bcrypt-hashed; sessions are server-side and revocable.
- The web app should run behind HTTPS (reverse proxy) before any real use,
  since it handles logins and sensitive routine data.

Known follow-up: the DB password existed in an earlier committed
`docker-compose.yml`, so it is in git history. Before handing the repository
to the client, rotate the DB password or start the repo history fresh.

## Operations

- Apply config changes (env, compose): recreate, never restart.
  `docker-compose down && docker-compose up -d`. `down` does not delete data;
  only `down -v` removes the volume.
- Both `db` and `collector` have `restart: unless-stopped`; the Docker daemon
  must be enabled (`systemctl enable docker`) so they return after a reboot.
- Health check: `SELECT count(*), min(ts), max(ts) FROM readings;` (expect
  ~120 rows/hour for two devices, `max(ts)` within ~2 minutes).
- Backup: a daily `pg_dump | gzip` off-box, with periodic restore checks.

### Compose V1 note

The legacy `docker-compose` 1.29 binary crashes with `ERROR: 'ContainerConfig'`
when recreating containers. Workaround: `docker-compose down` first, then
`docker-compose up -d`. Installing Compose V2 (invoked as `docker compose`,
with a space) removes the problem.

## Data notes

- Tuya reports `cur_power` in tenths of a watt and `cur_voltage` in tenths of a
  volt; the collector converts at ingestion.
- `add_ele` is an increment counter, not a running total; the collector
  accumulates it into `devices.total_ele_wh`.
- The device-list endpoint returns `online: None`; the per-device detail
  endpoint has the authoritative flag.
- Tuya's free "Trial Edition" of IoT Core has a limited quota/period. When
  exhausted, polls fail with `IoT Core trial quota is exhausted` and no data is
  collected until the subscription is extended on the Tuya account. Such gaps
  are excluded from learning and shown as SEM DADOS / SYSTEM.

## Roadmap

- Phase 1: Tuya integration, continuous collection, offline detection. Done.
- Phase 2: inference engine (routine learning, deviation detection,
  green/yellow/red states, offline-gap reconciliation). Done.
- Phase 3: web dashboard (Family/Caregiver + Admin profiles), sensitivity
  controls, and notifications (email + WhatsApp). Built.
- Phase 4: end-to-end testing, threshold tuning, deployment hardening,
  documentation and handover (including credential rotation).
