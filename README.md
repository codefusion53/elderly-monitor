# Elderly Monitoring System

Continuous collection of smart-plug telemetry (Tuya) with offline detection.
Core principle: **"no data" is never confused with "no activity"** — every
connectivity gap is detected, bounded, and recorded.

## Quick start
1. `cp .env.example .env` and fill in `TUYA_ACCESS_SECRET`.
2. `docker-compose up -d --build`
3. Watch it: `docker-compose logs -f collector`

The schema auto-applies on first start (seeded with the two test plugs).

## What runs
- **collector**: polls each plug every `POLL_INTERVAL_SECONDS` (default 60),
  stores watts/current/voltage/energy into `readings`, accumulates kWh,
  and drives the connectivity state machine
  (`online → offline_suspected → offline_confirmed`, tolerance window
  `OFFLINE_TOLERANCE_MINUTES`, default 20). Confirmed transitions are
  written to `connectivity_events`.

## Verify it works
- Coffee test: brew a coffee, then
  `SELECT ts, cur_power_w FROM readings WHERE device_id=1 ORDER BY ts DESC LIMIT 30;`
  and watch the spike.
- Offline test: unplug a device for 25+ minutes, then
  `SELECT * FROM connectivity_events ORDER BY ts DESC;`
  — expect `offline_confirmed`, then `back_online` after re-plugging.
