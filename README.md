# Elderly Monitoring System

Continuous collection of smart-plug telemetry (Tuya) with offline detection.

Core principle: **"no data" is never confused with "no activity"** — every
connectivity gap is detected, bounded, and recorded as a system event,
completely separate from the activity signal.

## Architecture

```
Smart plugs ──> Tuya Cloud API ──> collector (poll loop, 60s)
                                        │
                                        ├─> readings            (raw telemetry)
                                        ├─> devices             (live conn state, kWh totals)
                                        └─> connectivity_events (offline/online transitions)
```

- **collector/** — Python service. Polls each plug every `POLL_INTERVAL_SECONDS`
  (default 60), stores watts / current / voltage / energy increments, and
  drives the connectivity state machine.
- **schema.sql** — PostgreSQL schema, auto-applied on first start, seeded with
  the test residence and both plugs. Designed multi-residence from day one.

## Connectivity state machine

```
unknown ──> online ──> offline_suspected ──> offline_confirmed
              ^                │                     │
              └────────────────┴──── back_online ────┘
```

- A failed poll or `online=false` moves a device to `offline_suspected`.
  **Nothing is emitted** in this state — short Wi-Fi flickers trigger nothing.
- Only after `OFFLINE_TOLERANCE_MINUTES` (default 20) without a successful
  poll does the device become `offline_confirmed`, writing a row to
  `connectivity_events`. Recovery writes `back_online`, so every gap is
  bounded on both ends.
- The tolerance window is configurable and will be adjustable from the
  admin profile.

## Setup

1. `cp .env.example .env` and fill in the real values.
   `.env` is the **single source of truth** for credentials — it is
   git-ignored and must never be committed.
2. `docker compose up -d --build`
   (Compose **V2** recommended. See "Compose V1 quirks" below if you are
   stuck on the legacy `docker-compose` binary.)
3. Watch it: `docker compose logs -f collector`
   Expected output: one line per plug per minute, e.g.
   `Cafeteira cozinha: 0.0 W, switch=True, online=True`

The collector retries the database connection on startup (up to 30
attempts), so the DB/collector boot race resolves itself. A wrong password
fails immediately and loudly instead of retrying.

## Security posture (as deployed)

- **Database password**: changed from the default; lives only in `.env`
  and docker-compose.yml (keep both in sync — after changing it, run
  `ALTER USER monitor WITH PASSWORD '...'` inside the db container, then
  recreate the stack).
- **No public database exposure**: the Postgres port is bound to
  `127.0.0.1` only (`127.0.0.1:5432:5432`). Verify with
  `ss -tlnp | grep 5432` — it must never show `0.0.0.0:5432`.
  Note: Docker-published ports bypass UFW, so the binding itself is the
  security boundary, not the host firewall.
- **Secrets hygiene**: `.env` is git-ignored; history verified clean.
  Tuya Access Secret and DB password are scheduled for rotation at
  final handover.
- **Backups**: daily `pg_dump` via cron at 04:15 to `/opt/backups`,
  gzip-compressed, 14-day retention (`/opt/backups/backup_monitor.sh`).
  Restores were spot-checked after setup.

## Operations

- **Apply config changes** (env vars, compose edits): always recreate,
  never restart — `restart` keeps the old environment.
  ```
  docker-compose down && docker-compose up -d
  ```
  (`down` does NOT delete data; only `down -v` would remove the volume.)
- **Query the database**:
  ```
  docker-compose exec db psql -U monitor -d monitor
  ```
- **Health check**:
  ```
  SELECT count(*), min(ts), max(ts) FROM readings;
  ```
  Expect ~120 rows/hour (2 devices × 1/min) and `max(ts)` within the
  last 2 minutes.
- **Gap check** (collection continuity):
  ```
  SELECT ts - lag(ts) OVER (ORDER BY ts) AS gap, ts
  FROM (SELECT DISTINCT ts FROM readings) t
  ORDER BY gap DESC NULLS LAST LIMIT 5;
  ```

### Compose V1 quirks (legacy `docker-compose` 1.29)

Recreating existing containers crashes with `ERROR: 'ContainerConfig'`.
Workaround: `docker-compose down` first, then `docker-compose up -d`.
Avoid `--force-recreate` and `restart` for config changes. Installing
Compose V2 (`docker compose`) removes the problem entirely.

## Acceptance tests

- **Activity capture (coffee test)**: brew a coffee, then
  ```
  SELECT ts, cur_power_w FROM readings r
  JOIN devices d ON d.id = r.device_id
  WHERE d.name LIKE 'Cafeteira%' AND ts > now() - interval '1 hour'
  ORDER BY ts;
  ```
  Expect a spike from 0 into the hundreds of watts for a few minutes.
- **Offline detection**: unplug a device from the wall for 25+ minutes,
  replug, then
  ```
  SELECT * FROM connectivity_events ORDER BY ts DESC;
  ```
  Expect `offline_confirmed` ~20 min after unplugging and `back_online`
  shortly after replugging — and **no** inactivity misclassification.

## Tooling

- `make_progress_chart.py` — renders `progress_chart.png`: last 24h
  (configurable via `CHART_HOURS`) of power draw per device, local time
  (`CHART_TZ`, default Europe/Lisbon). Requires matplotlib; connects via
  `DATABASE_URL` from `.env`.
- `tuya_connection_test.py` — end-to-end Tuya check: auth, device list,
  live status with energy data points highlighted. Reads `.env`.
- `tuya_region_sweep.py` — raw token probe against every Tuya data
  center; diagnoses invalid/mislocated credentials in seconds. Reads `.env`.

## Data notes

- Tuya reports `cur_power` in tenths of a watt and `cur_voltage` in
  tenths of a volt; the collector converts to W and V at ingestion.
- `add_ele` is an **increment** counter, not a running total; the
  collector accumulates it into `devices.total_ele_wh`.
- The device-list endpoint returns `online: None`; the authoritative
  online flag comes from the per-device detail endpoint, which the
  collector fetches on every poll.