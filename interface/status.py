"""
Interface: current semáforo status (text).

Prints, per device, the live green/yellow/red state right now, using the
learned baseline plus the most recent activity and connectivity. This is the
text precursor to the Milestone 3 dashboard/notifications — it answers
"how is the person right now?" from the command line.

Run from project root, next to .env:
    python -m interface.status
"""
from __future__ import annotations

from datetime import datetime, timezone

from inference.baseline import learn_baseline, detect_activity_events
from inference.deviation import evaluate_state
from interface.data_access import connect, device_names, load_readings

ICON = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}


def main():
    conn = connect()
    try:
        now_local = None
        for name in device_names(conn):
            readings = load_readings(conn, name)
            if not readings:
                print(f"{name}: sem leituras.")
                continue
            base = learn_baseline(readings, name)

            # last activity event (local wall-clock, matching baseline space)
            events = detect_activity_events(readings)
            last_activity = events[-1] if events else None
            now_local = readings[-1].ts  # latest reading's local time as "now"

            # is the system currently online? last reading within ~3 intervals
            last_reading = readings[-1]
            system_online = bool(last_reading.online)

            res = evaluate_state(
                baseline=base,
                last_activity_ts=last_activity,
                now=now_local,
                system_online=system_online,
            )
            icon = ICON.get(res.state, "•")
            print(f"{icon} {name}  [{res.state} / {res.category}]")
            print(f"    {res.reason}")
            if res.minutes_since_activity is not None:
                print(f"    (última atividade há {res.minutes_since_activity:.0f} min)")
        if now_local:
            print(f"\nReferência temporal: última leitura às "
                  f"{now_local.strftime('%d/%m %H:%M')} (hora local).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
