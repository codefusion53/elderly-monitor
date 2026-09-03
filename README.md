# Elderly Monitoring System

Non-intrusive monitoring of an elderly person's wellbeing, inferred from the
electricity consumption of Wi-Fi smart plugs (Tuya ecosystem). The system
learns each home's normal routine, flags significant deviations, and always
keeps one principle central:

**"No data" is never confused with "no activity".** Every connectivity gap is
detected, bounded, and recorded as a system event, kept completely separate
from any statement about the person.

## Subsystems

The project has three layers, each in its own package:

```
collector/   Reads the plugs via the Tuya Cloud API every 60s, stores raw
             telemetry, and runs the connectivity state machine.
inference/   Learns the routine baseline from stored readings and decides the
             green / yellow / red state (the "brain").
interface/   Read-only reporting and visualization on top of the data:
             charts, live status, and the shared DB access layer.
```

```
Smart plugs --> Tuya Cloud API --> collector --> PostgreSQL
                                                    |
                                   inference  <-----+-----> interface
                                   (baseline,             (charts, status,
                                    deviation,             reports)
                                    states)
```

## collector/

Polls each plug every `POLL_INTERVAL_SECONDS` (default 60), converts Tuya's
tenths-of-a-watt / tenths-of-a-volt values to real units, accumulates the
`add_ele` energy increment, and writes to three tables:

- `readings` : append-only raw telemetry (power, current, voltage, switch, online).
- `devices` : live connectivity state and running kWh total per device.
- `connectivity_events` : every confirmed offline / online transition.

### Connectivity state machine

```
unknown --> online --> offline_suspected --> offline_confirmed
              ^               |                     |
              +---------------+---- back_online -----+
```

A failed poll or `online=false` moves a device to `offline_suspected`, and
nothing is emitted in that state, so short Wi-Fi flickers trigger nothing.
Only after `OFFLINE_TOLERANCE_MINUTES` (default 20) without a successful poll
does the device become `offline_confirmed`, writing a `connectivity_events`
row. Recovery writes `back_online`, so every gap is bounded on both ends.

Note on Tuya caching: when a plug is offline, `getstatus` may keep returning
the last cached values, so the authoritative liveness signal is the `online`
flag from the device-detail endpoint, which the collector fetches every poll.

## inference/

Learns the routine and decides the state. Tuned for sparse, single-strong-signal
data (a coffee maker that spikes for a few minutes, not a dense multi-appliance
routine).

- `baseline.py` : detects activity events (readings above a per-device wattage
  threshold, de-duplicated so one continuous use counts once), then learns
  per-hour activity probability, the typical and maximum gap between events,
  and the habitual quiet hours. Data gaps (device/collector/quota offline) are
  excluded from learning, so silence caused by no data is never learned as "a
  quiet day". Low-signal devices (e.g. an LED lamp) are excluded from activity
  inference but still monitored for connectivity.
- `deviation.py` : the green / yellow / red logic.
  - GREEN: activity recent enough, within normal patterns.
  - YELLOW: quiet stretch approaching the household's normal ceiling.
  - RED (activity): quiet stretch past the learned ceiling during waking hours.
  - RED (system): the plug/collector is offline. Reported as a system-health
    alert, explicitly distinct from the person being inactive.
  Habitual quiet hours (e.g. night) never trigger an activity alarm.
- `report.py` : the validation runner. Learns the baseline, then replays the
  history day by day, classifying each day GREEN / YELLOW / RED / SEM DADOS.
  A day observed but with no waking activity flags RED (the dangerous
  false-negative); a day not adequately observed flags SEM DADOS, never a
  falsely reassuring GREEN.

Run the validation report:

```
python -m inference.report
```

## interface/

Read-only tooling on top of the data. Nothing here writes to the database.

- `data_access.py` : shared DB access (one query path for all interface tools).
- `make_charts.py` : unified chart CLI.
  - `python -m interface.make_charts --routine` : learned routine + day-by-day
    state strip (the Phase 2 evidence chart).
  - `python -m interface.make_charts --consumption --hours 48` : power curve.
  - `python -m interface.make_charts --all`
  - `--out DIR` chooses the output directory.
- `make_routine_chart.py` / `make_progress_chart.py` : single-purpose
  equivalents of the two charts, for convenience.
  - `python -m interface.make_routine_chart`
  - `python -m interface.make_progress_chart`
- `status.py` : current semaforo state per device from the command line.
  - `python -m interface.status`

## check/

One-off diagnostics (read credentials from `.env`):

- `check/tuya_connection_test.py` : auth, device list, live status with energy
  data points highlighted.
- `check/tuya_region_sweep.py` : probes every Tuya data center to locate or
  rule out mislocated / invalid credentials in seconds.

## Setup

1. `cp .env.example .env` and fill in the real values. `.env` is the single
   source of truth for credentials; it is git-ignored and must never be
   committed. It must also define `DB_PASSWORD` (used by docker-compose to set
   and connect to Postgres).
2. `docker-compose up -d --build` (Compose V2 recommended; see the note below
   if stuck on the legacy binary).
3. Watch it: `docker-compose logs -f collector`. Expected: one line per plug
   per minute, e.g. `Cafeteira cozinha: 0.0 W, switch=True, online=True`.

The collector retries the database connection on startup (up to 30 attempts),
so the DB/collector boot race resolves itself. A wrong password fails
immediately and loudly instead of retrying.

## Security posture

- The database password lives only in `.env` (as `DB_PASSWORD`). It is no
  longer hardcoded in `docker-compose.yml`; the compose file interpolates
  `${DB_PASSWORD}`.
- No public database exposure: the Postgres port is bound to `127.0.0.1` only.
  Verify with `ss -tlnp | grep 5432`; it must never show `0.0.0.0:5432`.
  Docker-published ports bypass UFW, so the binding itself is the boundary.
- `.env` is git-ignored; `.env.example` is the committable template.
- Daily `pg_dump` backup via cron is recommended (see Operations).

Known follow-up: the database password was present in an earlier committed
version of `docker-compose.yml`, so it exists in git history. Before handing
the repository to the client, either rotate the DB password or start the repo
history fresh.

## Operations

- Apply config changes (env vars, compose edits): always recreate, never
  restart. `docker-compose down && docker-compose up -d`. `down` does not
  delete data; only `down -v` would remove the volume.
- Both `db` and `collector` have `restart: unless-stopped`, so they come back
  automatically after a host reboot (the daemon must be enabled:
  `systemctl is-enabled docker`, and `systemctl enable docker` if not).
- Query the database: `docker-compose exec db psql -U monitor -d monitor`.
- Health check: `SELECT count(*), min(ts), max(ts) FROM readings;`
  (expect about 120 rows/hour for two devices, `max(ts)` within ~2 minutes).
- Backup: a daily `pg_dump | gzip` to an off-box location, with a periodic
  restore spot-check.

### Compose V1 note

The legacy `docker-compose` 1.29 binary crashes with
`ERROR: 'ContainerConfig'` when recreating containers. Workaround:
`docker-compose down` first, then `docker-compose up -d`. Installing Compose
V2 (`docker-compose`) removes the problem.

## Data notes

- Tuya reports `cur_power` in tenths of a watt and `cur_voltage` in tenths of a
  volt; the collector converts to W and V at ingestion.
- `add_ele` is an increment counter, not a running total; the collector
  accumulates it into `devices.total_ele_wh`.
- The device-list endpoint returns `online: None`; the authoritative online
  flag comes from the per-device detail endpoint.
- Tuya's free "Trial Edition" of IoT Core has a limited quota/period. When it
  is exhausted, polls fail with `IoT Core trial quota is exhausted` and no new
  data is collected until the subscription is extended on the Tuya account.
  Such gaps are excluded from routine learning and shown as SEM DADOS.

## Roadmap

- Phase 1: Tuya integration, continuous collection, offline detection.
  Done and delivered.
- Phase 2: inference engine (routine learning, deviation detection,
  green/yellow/red states, offline-gap reconciliation). Built and validated.
- Phase 3: web dashboard (Family/Caregiver + Admin profiles), push + SMS
  notifications, WhatsApp Business integration.
- Phase 4: end-to-end testing, threshold tuning, deployment hardening,
  documentation and handover (including credential rotation).