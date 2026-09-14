"""
Live state service (with system-health / data-freshness).

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

STALE_AFTER_MINUTES = 10


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


def compute_device_state(conn, device):
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

    res = evaluate_state(baseline, last_activity, now, system_online)

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
    )
    return ds, now


def compute_all_states():
    conn = connect()
    try:
        devices, latest_ts = [], None
        for name in device_names(conn):
            ds, last_ts = compute_device_state(conn, name)
            devices.append(asdict(ds))
            if last_ts and (latest_ts is None or last_ts > latest_ts):
                latest_ts = last_ts

        stale_minutes, system_ok = None, True
        if latest_ts is not None:
            now_local = datetime.now()
            base = latest_ts.replace(tzinfo=None) if latest_ts.tzinfo else latest_ts
            stale_minutes = max(0, (now_local - base).total_seconds() / 60)
            system_ok = stale_minutes <= STALE_AFTER_MINUTES

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
    order = {"GREEN": 0, "YELLOW": 1, "RED": 2}
    activity = [d for d in devices if d["ceiling_min"]]
    worst, reason, category = "GREEN", "Tudo normal.", "activity"
    for d in (activity or devices):
        if order.get(d["state"], 0) > order.get(worst, 0):
            worst, reason, category = d["state"], d["reason"], d["category"]
    return {"state": worst, "reason": reason, "category": category}


if __name__ == "__main__":
    import json
    print(json.dumps(compute_all_states(), indent=2, ensure_ascii=False))