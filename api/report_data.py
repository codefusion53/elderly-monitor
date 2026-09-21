"""
Phase 3 - Report data assembly for the admin report page.

Pulls together, per residence, a readable summary of what the system has
learned and observed (Option A) plus the event history (Option B):
  - learned routine summary (peak hours, gaps, quiet hours)
  - day-by-day state validation over the window
  - connectivity event history (offline / back_online)
  - alert history (what was notified, when, to whom)

Read-only. Everything comes from tables the collector/alerting already fill.
"""
from __future__ import annotations

from datetime import datetime

from inference.baseline import learn_baseline, detect_activity_events
from inference.report import validate_days
from interface.data_access import connect, device_names, load_readings, TZ

WINDOW_DAYS = 14


def _routine_summaries(conn, window_days=WINDOW_DAYS):
    out = []
    for name in device_names(conn):
        readings = load_readings(conn, name)
        if not readings:
            out.append({"device": name, "signal": False, "reason": "sem leituras"})
            continue
        base = learn_baseline(readings, name)
        if base.total_active_events == 0:
            out.append({"device": name, "signal": False,
                        "reason": "sinal fraco (monitorizado apenas para conectividade)"})
            continue
        peaks = [h for h, _ in sorted(base.hourly_activity_prob.items(),
                 key=lambda kv: kv[1], reverse=True)[:3]]
        out.append({
            "device": name, "signal": True,
            "days_observed": round(base.days_observed, 1),
            "events": base.total_active_events,
            "peak_hours": sorted(peaks),
            "typical_gap_min": round(base.typical_gap_min),
            "ceiling_min": round(base.max_normal_gap_min),
            "quiet_hours": sorted(base.quiet_hours),
            "days": validate_days(readings, base)[-window_days:],
        })
    return out


def _connectivity_events(conn, limit=40):
    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT d.name, e.event_type,
                       (e.ts AT TIME ZONE %s) AS local_ts, e.detail
                FROM connectivity_events e JOIN devices d ON d.id = e.device_id
                ORDER BY e.ts DESC LIMIT %s""",
            (TZ, limit))
        return [{"device": r[0], "type": r[1],
                 "ts": r[2].strftime("%d/%m %H:%M"), "detail": r[3]}
                for r in cur.fetchall()]


def _alert_history(conn, limit=40):
    with conn.cursor() as cur:
        # alert_log may be empty if no alerts fired yet
        try:
            cur.execute(
                f"""SELECT (ts AT TIME ZONE %s), channel, to_addr, tier,
                           state, subject, ok
                    FROM alert_log ORDER BY ts DESC LIMIT %s""",
                (TZ, limit))
            return [{"ts": r[0].strftime("%d/%m %H:%M"), "channel": r[1],
                     "to": r[2], "tier": r[3], "state": r[4],
                     "subject": r[5], "ok": r[6]} for r in cur.fetchall()]
        except Exception:
            return []


def build_report(window_days=WINDOW_DAYS):
    conn = connect()
    try:
        return {
            "generated": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "window_days": window_days,
            "routines": _routine_summaries(conn, window_days),
            "connectivity": _connectivity_events(conn),
            "alerts": _alert_history(conn),
        }
    finally:
        conn.close()
