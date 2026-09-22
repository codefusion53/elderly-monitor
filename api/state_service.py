"""
Phase 3 - Live state service (with system-health / data-freshness).

Computes green/yellow/red per device from the inference engine, PLUS a
system-health check on data freshness. If the newest reading is stale, the
residence rollup reports a SYSTEM state instead of presenting an activity
verdict computed from old data. This is the dashboard embodiment of
"no data is never no activity".
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime

from inference.baseline import learn_baseline, detect_activity_events
from inference.deviation import evaluate_state
from interface.data_access import connect, device_names, load_readings, live_state_rows

try:
    from api.auth import get_settings as _get_settings
except Exception:  # auth optional; fall back to defaults if unavailable
    _get_settings = None


def _residence_settings():
    """Load settings for the (single) residence. Extendable to multi-residence
    by keying on residence_id; the current DB has one residence."""
    if _get_settings is None:
        return {"yellow_fraction": 0.75, "stale_after_min": STALE_AFTER_MINUTES,
                "ceiling_override_min": None}
    try:
        return _get_settings(1)
    except Exception:
        return {"yellow_fraction": 0.75, "stale_after_min": STALE_AFTER_MINUTES,
                "ceiling_override_min": None}

STALE_AFTER_MINUTES = 10

# During the first days after a new kit is installed, the learned baseline is
# not yet trustworthy. Until an activity-signal device has been observed for at
# least this many days, the residence reports "CALIBRATION" (Em Aprendizagem)
# instead of a green/yellow/red activity verdict.
CALIBRATION_DAYS = 14


def _human_ago(minutes):
    if minutes is None:
        return None
    m = int(minutes)
    if m < 60:
        return f"há {m} min"
    h = m // 60
    if h < 24:
        return f"há {h}h{m % 60:02d}"
    d = h // 24
    return f"há {d} dia{'s' if d != 1 else ''}"


@dataclass
class DeviceState:
    device: str
    state: str
    category: str
    reason: str
    minutes_since_activity: float | None
    last_activity_human: str | None
    ceiling_min: float
    conn_state: str | None
    last_reading: str | None
    peak_hours: list = field(default_factory=list)
    events_today: int = 0
    days_observed: float = 0.0


def compute_device_state(conn, device, settings=None):
    settings = settings or {}
    readings = load_readings(conn, device)
    conn_state = None
    for row in live_state_rows(conn):
        if row["name"] == device:
            conn_state = row["conn_state"]

    if not readings:
        return DeviceState(device, "RED", "system",
                           "Sem leituras para este dispositivo.",
                           None, None, 0.0, conn_state, None), None

    baseline = learn_baseline(readings, device)
    events = detect_activity_events(readings)
    last_activity = events[-1] if events else None
    now = readings[-1].ts
    system_online = readings[-1].online and conn_state != "offline_confirmed"

    res = evaluate_state(
        baseline, last_activity, now, system_online,
        yellow_fraction=settings.get("yellow_fraction"),
        ceiling_override_min=settings.get("ceiling_override_min"),
    )

    peaks = ([h for h, _ in sorted(baseline.hourly_activity_prob.items(),
             key=lambda kv: kv[1], reverse=True)[:2]]
             if baseline.total_active_events else [])
    events_today = sum(1 for e in events if e.date() == now.date())
    last_activity_human = last_activity.strftime("%H:%M") if last_activity else None

    ds = DeviceState(
        device=device, state=res.state, category=res.category, reason=res.reason,
        minutes_since_activity=res.minutes_since_activity,
        last_activity_human=last_activity_human,
        ceiling_min=res.ceiling_min, conn_state=conn_state,
        last_reading=now.strftime("%Y-%m-%d %H:%M"),
        peak_hours=sorted(peaks), events_today=events_today,
        days_observed=round(baseline.days_observed, 1),
    )
    return ds, now


def _minutes_since_last_reading(conn):
    """Minutes since the most recent reading, computed entirely in the database
    in absolute time (UTC). This is timezone- and DST-independent: it never
    mixes the server's local clock with the Lisbon wall-clock. Returns None if
    there are no readings.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXTRACT(EPOCH FROM (now() - max(ts))) / 60 FROM readings")
        row = cur.fetchone()
        return float(row[0]) if row and row[0] is not None else None


def compute_all_states():
    conn = connect()
    try:
        settings = _residence_settings()
        stale_after = settings.get("stale_after_min") or STALE_AFTER_MINUTES

        devices, latest_ts = [], None
        for name in device_names(conn):
            ds, last_ts = compute_device_state(conn, name, settings)
            devices.append(asdict(ds))
            if last_ts and (latest_ts is None or last_ts > latest_ts):
                latest_ts = last_ts

        stale_minutes, system_ok = None, True
        # staleness is computed in absolute UTC by the database (DST-safe),
        # not by mixing the server clock with local wall-clock timestamps.
        sm = _minutes_since_last_reading(conn)
        if sm is not None:
            stale_minutes = max(0, sm)
            system_ok = stale_minutes <= stale_after

        residence = _residence_rollup(devices, system_ok, stale_minutes)
        return {"devices": devices, "residence": residence,
                "system": {"ok": system_ok, "stale_minutes": stale_minutes,
                           "stale_human": _human_ago(stale_minutes)}}
    finally:
        conn.close()


def _residence_rollup(devices, system_ok, stale_minutes):
    if not system_ok:
        return {"state": "SYSTEM", "category": "system",
                "reason": f"Sistema sem dados recentes ({_human_ago(stale_minutes)}). "
                          f"Não é possível confirmar atividade em tempo real."}
    # Calibration: while the system is still learning the routine (fewer than
    # CALIBRATION_DAYS observed on any activity-signal device), do not present a
    # normal activity verdict, the baseline is not yet reliable.
    activity = [d for d in devices if d["ceiling_min"]]
    if activity:
        max_days = max(d.get("days_observed", 0) for d in activity)
        if max_days < CALIBRATION_DAYS:
            remaining = max(0, CALIBRATION_DAYS - max_days)
            return {"state": "CALIBRATION", "category": "system",
                    "reason": f"Em aprendizagem: o sistema está a conhecer a rotina "
                              f"da casa ({max_days:.0f} de {CALIBRATION_DAYS} dias). "
                              f"Os alertas de inatividade ficam mais fiáveis dentro "
                              f"de ~{remaining:.0f} dias."}
    order = {"GREEN": 0, "YELLOW": 1, "RED": 2}
    worst, reason, category = "GREEN", "Tudo normal.", "activity"
    for d in (activity or devices):
        if order.get(d["state"], 0) > order.get(worst, 0):
            worst, reason, category = d["state"], d["reason"], d["category"]
    return {"state": worst, "reason": reason, "category": category}


if __name__ == "__main__":
    import json
    print(json.dumps(compute_all_states(), indent=2, ensure_ascii=False))
