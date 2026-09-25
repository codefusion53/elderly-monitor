# Tuya Events Migration - Design (Phase 4)

## Why
Polling consumes ~170k Tuya API calls/month (2 devices x ~2 calls/min),
far above the free 25k/month quota. Even the polling optimisation (~40% cut)
stays well over. The structural fix is to stop polling and instead subscribe
to Tuya's Message Service (Pulsar), which pushes an event only when a device
changes state. For 2 low-activity plugs this is a tiny message volume.

## How Tuya Message Service works
- Tuya pushes device events over a Pulsar message queue.
- Subscribe with the existing Access ID / Access Secret.
- EU region Pulsar endpoint: pulsar+ssl://mqe.tuyaeu.com:7285/
  (mirrors our TUYA_REGION=eu; other regions: tuyaus, tuyacn ...).
- Event types we care about:
    dp_report  -> a device reported data (power / switch changes) => a reading
    online     -> device came online                              => connectivity
    offline    -> device went offline                             => connectivity
- Message payloads are encrypted with the Access Secret (AES); the SDK / a
  small decrypt step recovers the JSON.
- Billed per forwarded message. Must be enabled + authorised on the project.

## Architecture change
Before:  a timer loop calls the Tuya API every 60s (pull).
After:   a long-lived consumer holds a Pulsar connection and reacts to
         pushed events (listen).

The rest of the system does NOT change:
- readings, devices, connectivity_events tables: unchanged.
- inference (baseline, deviation), api, alerting: unchanged, they read the
  same tables. This is the big win: only the collection layer changes.

New component: collector/events.py (a Pulsar consumer) that, on each event,
writes to the same DB via the existing db.py helpers, so downstream is
identical to what the poller produced.

### Mapping events to the existing schema
- dp_report: parse the status data points (cur_power, cur_voltage, add_ele,
  switch_1), convert units exactly as tuya_client does today, insert a row in
  readings. Mark online=True (a reporting device is online).
- online:  connectivity.on_poll_result(poll_ok=True, reported_online=True)
- offline: connectivity.on_poll_result(poll_ok=False, reported_online=False)
  (feeds the SAME state machine, so offline_confirmed / back_online logic and
  the tolerance window keep working unchanged.)

### Reliability requirements (the real engineering)
1. Reconnect automatically if the Pulsar connection drops, without losing
   messages (Pulsar retains unacked messages; ack only after a successful DB
   write).
2. A heartbeat / "last event or keepalive" so the system-health / stale-data
   detection still works. Note: with events, "no data" is normal when the
   person is inactive, so staleness must be judged differently, e.g. a
   periodic lightweight liveness check or Tuya's online/offline events rather
   than "no reading in N minutes". THIS IS A KEY DESIGN POINT (see below).
3. Run as its own service in docker-compose (replacing, or alongside during
   transition, the collector service).

### Important nuance: staleness detection changes meaning
With polling, "no reading in 10 min" = system blind = SYSTEM state. With
events, silence is EXPECTED (events only arrive on change), so we cannot treat
"no recent event" as "system down". Instead:
- rely on Tuya online/offline events for connectivity, and
- keep a low-frequency liveness ping (e.g. one cloud call every 30-60 min) OR
  use Pulsar connection health as the "system up" signal.
This is why the migration is more than a transport swap: the freshness/health
logic must be rethought for an event world. Scoped accordingly.

## Transition plan
1. Build events.py consumer; run it in the TEST channel first (MQ_ENV_TEST)
   to validate parsing without touching production data.
2. Run events consumer and poller in parallel briefly; compare that events
   produce equivalent readings.
3. Cut over: switch the docker-compose collection service from poller to
   events consumer; keep a minimal low-frequency liveness check for health.
4. Confirm API call volume drops under 25k/month with real data.

## Dependencies
- tuya-pulsar SDK (or the documented Pulsar client + Tuya auth/decrypt).
- Message Service enabled and authorised on the client's Tuya project.
- Confirmation that message volume stays within the free/cheap tier.
