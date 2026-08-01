"""Connectivity state machine.

Core principle sold to the client: "no data" must NEVER be confused with
"no activity". This module owns that distinction.

States (stored on devices.conn_state):
    unknown            -> before the first successful poll
    online             -> polls succeeding, device reports online
    offline_suspected  -> a poll failed or online=false, but still inside
                          the tolerance window; NOTHING is emitted
    offline_confirmed  -> tolerance window exceeded; a connectivity_event
                          row is written (Milestone 3 will alert on these)

Transitions back to online from any offline state emit a 'back_online'
event so the gap is bounded on both ends (Milestone 2 reconciles it).
"""

from datetime import datetime, timedelta, timezone

from . import config, db

TOLERANCE = timedelta(minutes=config.OFFLINE_TOLERANCE_MINUTES)


def on_poll_result(conn, device: dict, poll_ok: bool, reported_online):
    """Advance one device's state machine after a poll attempt.

    device: row dict from db.fetch_devices (pre-poll state)
    poll_ok: True if the API call succeeded and telemetry was stored
    reported_online: the online flag from Tuya (may be None if unavailable)
    """
    state = device["conn_state"]
    now = datetime.now(timezone.utc)

    healthy = poll_ok and reported_online is not False

    if healthy:
        db.mark_poll_success(conn, device["id"])
        if state in ("offline_suspected", "offline_confirmed", "unknown"):
            if state == "offline_confirmed":
                db.insert_connectivity_event(
                    conn, device["id"], "back_online",
                    f"{device['name']} voltou a comunicar",
                )
            db.set_conn_state(conn, device["id"], "online")
        return

    # --- unhealthy poll ---
    if state in ("online", "unknown"):
        db.set_conn_state(conn, device["id"], "offline_suspected")
        return

    if state == "offline_suspected":
        last_ok = device["last_successful_poll"]
        suspected_since = device["conn_state_since"] or now
        reference = max(
            [t for t in (last_ok, suspected_since) if t is not None],
            default=suspected_since,
        )
        if now - reference >= TOLERANCE:
            db.set_conn_state(conn, device["id"], "offline_confirmed")
            db.insert_connectivity_event(
                conn, device["id"], "offline_confirmed",
                f"{device['name']} sem comunicação há "
                f"{config.OFFLINE_TOLERANCE_MINUTES}+ minutos",
            )
    # offline_confirmed + still failing -> stay put, no repeated events
