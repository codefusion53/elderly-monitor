# Zelo Smart — Elderly Monitoring System

Non-intrusive monitoring of an elderly person's wellbeing, inferred from the
electricity consumption of Wi-Fi smart plugs (Tuya ecosystem). The system
learns each home's normal routine, flags significant deviations, shows a
live traffic-light dashboard, and notifies family when something is wrong.

One principle stays central throughout:

**"No data" is never confused with "no activity".** Every connectivity gap is
detected, bounded, and reported as a system event, kept completely separate
from any statement about the person.

> For step-by-step production deployment (Docker stack, nginx reverse proxy,
> domain, HTTPS, and the public installation page), see **[INSTALLATION.md](INSTALLATION.md)**.

## Subsystems

```
collector/   Reads the plugs via the Tuya Cloud API every 60s, stores raw
             telemetry, runs the connectivity state machine.
inference/   Learns the routine baseline and decides green/yellow/red (brain).
interface/   Read-only reporting/visualization: charts, shared DB access.
api/         FastAPI web layer: live state API, dashboard, login, two
             profiles (Family/Caregiver + Admin), sensitivity settings,
             the alerting engine (email + WhatsApp), and the public pages
             (support/FAQ, privacy policy).
```

The whole system runs as one docker-compose stack of four services
(`db`, `collector`, `web`, `alerting`), all set to restart automatically.
In production, host nginx sits in front as an HTTPS reverse proxy.

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

**API-quota optimisation.** Fetching the authoritative `online` flag costs an
extra Tuya call per device, so the collector fetches it only every
`ONLINE_CHECK_EVERY` cycles (default 5) and reuses the last known value in
between; the power reading still happens every cycle. This roughly halves the
total call volume.

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
endpoint.

### Phase 4: events (Pulsar) path

`collector/events.py` and `collector/pulsar_test.py` implement an
event-driven alternative to polling, using the Tuya Message Service
(`tuya-connector-python`, Pulsar). Instead of calling the API on a timer, the
collector subscribes to `dp_report` / `online` / `offline` events that Tuya
pushes. This moves load from the tight API-call quota onto the much larger
message quota, which is the structural fix for the Trial-tier limit and the
basis for scaling to many homes. Polling remains the default running mode;
the events path is activated once the paid Tuya plan and a console Messaging
Rule (Production env, BizCodes online/offline/dp_report) are in place.

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

Read-only tooling on top of the collected data. Nothing here writes to the
database. `data_access.py` is the shared DB layer used by the charts and the
api.

`make_charts.py` is the chart CLI. Run it from the project root, next to
`.env`:

```
python -m interface.make_charts --all              # routine + consumption
python -m interface.make_charts --routine          # learned routine only
python -m interface.make_charts --consumption --hours 48   # power curve
python -m interface.make_charts --routine --out reports/   # choose output dir
```

- `--routine` renders, per device with a usable signal, the learned routine
  plus a day-by-day state strip (GREEN / YELLOW / RED / SEM DADOS). Output:
  `routine.png`.
- `--consumption` renders the last N hours (default 48) of power draw per
  device. Output: `consumption.png`.
- `--all` (default) renders both. `--out DIR` sets the output directory.
- Time zone follows `CHART_TZ` (default Europe/Lisbon).

## api/  (web layer)

FastAPI app serving the live system, the family/admin experience, and the
public pages. It runs as the `web` service in docker-compose. Run directly
during development:

```
pip install -r requirements.txt
uvicorn api.app:app --host 127.0.0.1 --port 8000
```

Pages and endpoints:

| Route | Access | Purpose |
|---|---|---|
| `GET /login`, `POST /api/login`, `GET /api/logout` | public | session auth |
| `GET /` | caregiver/admin | live dashboard (semáforo, routine chips, freshness banner); auto-refresh 60s |
| `GET /api/state` | caregiver/admin | JSON: per-device states + residence rollup + system health |
| `GET /admin`, `POST /api/settings/{residence_id}` | admin | per-residence sensitivity controls |
| `GET /admin/charts` | admin | routine + consumption charts |
| `GET /admin/report` | admin | day-by-day validation report (`?days=N`) |
| `GET /suporte` | caregiver/admin | support / FAQ page |
| `GET /privacidade` | **public** | privacy policy page (no login; linked from login + dashboard footer) |
| `GET /api/health` | public | `{"ok":true}` liveness probe (used by uptime monitoring) |

Roles: `caregiver` (dashboard + support only), `admin` (everything). All
`/admin*` routes return 403 for non-admins; the dashboard hides the admin link
for caregivers. No technical control is exposed to the caregiver view.

### System health / data freshness

If the newest reading is older than the residence's `stale_after_min`, the
dashboard shows a SYSTEM state ("Sistema sem dados") instead of an activity
verdict computed from stale data — the "no data is never no activity"
principle enforced in the UI.

### Alerting (api/alerting.py, api/notify.py)

Stateful engine: each cycle computes the current state, compares to the
last-notified state, and notifies only on CHANGE (never spams a stable state).

Tiering:
- routine (YELLOW, return-to-GREEN): email to `all`-tier contacts.
- critical (RED activity; any single plug offline past `EXTENDED_OFFLINE_MIN`;
  ALL plugs offline past `TOTAL_OFFLINE_CRITICAL_MIN`): WhatsApp + email to all.
- CALIBRATION (first days of a new kit) never alerts.

Channels (`api/notify.py`): email via SMTP (Brevo relay in production) and
WhatsApp via a Twilio-style Business API (needs a production Twilio account +
Meta-approved template; the code is ready and gated on that account). Both
fail safely if unconfigured.

Runs as the `alerting` service (a loop every 300s). Manually:
`python -m api.alerting` (one cycle) or `python -m api.alerting --loop 300`.

### Public installation page

The customer-facing Smart Life pairing guide (5 steps) is a single
self-contained static HTML page, served by nginx at
`https://zelosmart.tech/instalar` and encoded in the QR printed on each kit.
It is independent of the app, so it stays available even if the monitoring
stack is restarting. See INSTALLATION.md.

## check/

Diagnostics (read `.env`): `tuya_connection_test.py` (auth, device list, live
status) and `tuya_region_sweep.py` (locate/rule out mislocated credentials).

## Quick setup (development / single box)

Full production steps are in **[INSTALLATION.md](INSTALLATION.md)**. In short:

1. `cp .env.example .env` and fill in real values, including `DB_PASSWORD`.
   `.env` is git-ignored and must never be committed.
2. `sudo systemctl enable docker` (so the stack auto-starts after reboot).
3. `docker compose up -d --build`.
4. Schema: applied automatically on a fresh DB. On an existing DB that predates
   the alert-threshold columns, run the idempotent migration once:
   ```
   docker compose exec -T db psql -U monitor -d monitor -c "ALTER TABLE residence_settings ADD COLUMN IF NOT EXISTS extended_offline_min INTEGER NOT NULL DEFAULT 180, ADD COLUMN IF NOT EXISTS total_offline_critical_min INTEGER NOT NULL DEFAULT 40;"
   ```
5. Create an admin user:
   ```
   docker compose exec web python -c "from api.auth import create_user; create_user('admin','PICK_A_PASSWORD',role='admin')"
   ```
6. Verify: `docker compose ps` (all four `Up`) and
   `curl -s localhost:8000/api/health` → `{"ok":true}`.

### .env keys

```
TUYA_REGION, TUYA_ACCESS_ID, TUYA_ACCESS_SECRET        # Tuya API
DB_PASSWORD, DATABASE_URL                              # database (same password)
POLL_INTERVAL_SECONDS, OFFLINE_TOLERANCE_MINUTES       # collector timing
ONLINE_CHECK_EVERY                                     # collector quota saving (default 5)
CHART_TZ                                               # charts/report timezone (default Europe/Lisbon)
SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM  # email alerts (Brevo in prod)
WHATSAPP_API_URL, WHATSAPP_API_TOKEN, WHATSAPP_FROM    # WhatsApp alerts
WHATSAPP_CONTENT_SID                                   # approved WhatsApp template id
```
Alert thresholds `extended_offline_min` and `total_offline_critical_min` are
per-residence columns in `residence_settings` (defaults 180 / 40), editable in
the admin settings page. `.env` values are read literally: no quotes, no
trailing spaces.

## Security posture

- The database password lives only in `.env` (`DB_PASSWORD`); compose
  interpolates `${DB_PASSWORD}`. Postgres is bound to `127.0.0.1` only — verify
  with `ss -tlnp | grep 5432` (must never show `0.0.0.0:5432`).
- Passwords are bcrypt-hashed; sessions are server-side and revocable.
- The web app runs behind nginx + HTTPS (Let's Encrypt) in production.
- **Credential rotation** is part of hardening: any secret shared over chat
  during setup (VPS, Tuya, Twilio, Brevo, DB) should be rotated before launch,
  and the DB password that existed in an earlier committed compose file is in
  git history — rotate it or start the repo history fresh before handover.

## Operations

- Config changes (env, compose): recreate, never restart —
  `docker compose down && docker compose up -d`. `down` keeps data; only
  `down -v` removes the volume.
- Code changes: rebuild so `web`/`collector`/`alerting` pick it up —
  `docker compose up -d --build`.
- Logs: `docker compose logs -f collector` (or `web`, `alerting`, `db`).
- Health: `SELECT count(*), min(ts), max(ts) FROM readings;`
  (~120 rows/hour for two devices; `max(ts)` within ~2 minutes).
- Backup: daily `pg_dump | gzip` off-box, with periodic restore checks.

### Compose V1 note

The legacy `docker-compose` 1.29 binary crashes with `ERROR: 'ContainerConfig'`
on recreate. Workaround: `docker-compose down` then `docker-compose up -d`.
Installing Compose V2 (`docker compose`, with a space) removes the problem.

## Data notes

- Tuya reports `cur_power` in tenths of a watt and `cur_voltage` in tenths of a
  volt; the collector converts at ingestion.
- `add_ele` is an increment counter, not a running total; the collector
  accumulates it into `devices.total_ele_wh`.
- The device-list endpoint returns `online: None`; the per-device detail
  endpoint has the authoritative flag.
- Tuya's free "Trial Edition" of IoT Core has a limited quota and prohibits
  commercial use. When the quota is exhausted, polls fail with a quota error
  and no data is collected until a paid plan is active. Such gaps are excluded
  from learning and shown as SEM DADOS / SYSTEM.

## Roadmap

- Phase 1: Tuya integration, continuous collection, offline detection. ✓
- Phase 2: inference engine (routine learning, deviation detection, states). ✓
- Phase 3: web dashboard (Caregiver + Admin), sensitivity controls,
  notifications (email + WhatsApp). ✓
- Phase 4: events migration design, polling optimisation, deployment hardening
  (nginx, HTTPS, public install page), privacy page, documentation. ✓
- Commercialisation (planned): registration + payment, customer-panel polish,
  paid Tuya plan cutover, external server watchdog. See the commercialisation
  plan for scope and sequencing.