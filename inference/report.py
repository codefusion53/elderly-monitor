"""
Validation runner.

Connects to the collector's database, loads the real readings, learns the
routine baseline per device, then REPLAYS the history to show:
  - the routine the system learned (busiest hours, gaps, quiet hours)
  - a day-by-day validation: for each historical day, how many activity
    events, the longest quiet stretch during waking hours, and whether that
    day would have been flagged YELLOW/RED.

This produces the deliverable evidence: "here is the routine your
system learned from your real data, and here is where it would have alerted."

Run (from the project root, next to .env):
    python -m inference.report
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import timedelta

import psycopg2
from dotenv import load_dotenv

from .baseline import Reading, detect_activity_events, learn_baseline
from .deviation import evaluate_state

load_dotenv()
DATABASE_URL = os.getenv(
    "DATABASE_URL"
)
TZ = os.getenv("CHART_TZ", "Europe/Lisbon")


def load_readings(conn, device_name: str) -> list[Reading]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT (r.ts AT TIME ZONE %s) AS local_ts,
                   COALESCE(r.cur_power_w, 0), COALESCE(r.online, true)
            FROM readings r JOIN devices d ON d.id = r.device_id
            WHERE d.name = %s
            ORDER BY r.ts
            """,
            (TZ, device_name),
        )
        out = []
        for ts, power, online in cur.fetchall():
            # ts comes back naive (already shifted to local); attach nothing,
            # baseline logic only needs consistent local wall-clock.
            out.append(Reading(ts=ts, device=device_name,
                               power_w=float(power), online=bool(online)))
        return out


def device_names(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM devices ORDER BY id")
        return [r[0] for r in cur.fetchall()]


def validate_days(readings, baseline):
    """Per-day flag. Distinguishes three cases that must never be confused:
      SEM DADOS - the day was not adequately observed (device/collector/quota
                  offline for most of it). Not a statement about the person.
      RED       - the day WAS observed but shows no/too-little activity during
                  waking hours -> the dangerous false-negative scenario.
      YELLOW/GREEN - observed and within/near normal patterns.
    """
    from datetime import timedelta

    # how many minutes of each day were actually observed (online readings)
    obs_minutes = defaultdict(int)
    by_day = defaultdict(list)
    for r in readings:
        by_day[r.ts.date()].append(r)
        if r.online:
            obs_minutes[r.ts.date()] += 1  # ~1 reading/min

    # waking minutes per day = minutes not in habitual quiet hours
    waking_hours = [h for h in range(24) if h not in baseline.quiet_hours]
    waking_minutes_full = len(waking_hours) * 60

    # a day needs at least this fraction of its WAKING window observed to
    # be judged on activity; otherwise it's SEM DADOS.
    MIN_COVERAGE = 0.6

    rows = []
    for day in sorted(by_day):
        events = detect_activity_events(by_day[day])
        waking_events = [e for e in events if e.hour not in baseline.quiet_hours]

        # observed waking minutes this day
        observed_waking = sum(
            1 for r in by_day[day]
            if r.online and r.ts.hour not in baseline.quiet_hours
        )
        coverage = (observed_waking / waking_minutes_full) if waking_minutes_full else 0

        if coverage < MIN_COVERAGE:
            rows.append((day, len(events), None, "SEM DADOS"))
            continue

        # observed enough. Measure the worst waking silence, INCLUDING the
        # stretches before the first and after the last event within the
        # observed waking window (a fully silent day must not read as gap 0).
        ceiling = baseline.max_normal_gap_min or 0.0
        if not waking_events:
            # observed a normal waking day with zero activity -> worst case
            worst = waking_minutes_full
        else:
            worst = 0.0
            for a, b in zip(waking_events, waking_events[1:]):
                worst = max(worst, (b - a).total_seconds() / 60)

        flag = "GREEN"
        if ceiling:
            if worst >= ceiling:
                flag = "RED"
            elif worst >= 0.75 * ceiling:
                flag = "YELLOW"
        rows.append((day, len(events), worst, flag))
    return rows


def main():
    conn = psycopg2.connect(DATABASE_URL)
    print("=" * 66)
    print("INFERENCE ENGINE VALIDATION REPORT")
    print("=" * 66)

    for name in device_names(conn):
        readings = load_readings(conn, name)
        if not readings:
            print(f"\n[{name}] no readings.")
            continue
        baseline = learn_baseline(readings, name)

        print(f"\n{'-'*66}\nDEVICE: {name}   ({len(readings):,} readings)")
        print("-" * 66)
        print(baseline.summary())

        if baseline.total_active_events == 0:
            print("  -> Low/'no' activity signal; excluded from routine "
                  "inference (still monitored for connectivity).")
            continue

        print("\n  Day-by-day validation:")
        print(f"  {'Data':<12}{'Eventos':>8}{'Maior silêncio (min)':>22}{'Estado':>9}")
        for day, n_events, worst, flag in validate_days(readings, baseline):
            worst_str = "-" if worst is None else f"{worst:.0f}"
            print(f"  {str(day):<12}{n_events:>8}{worst_str:>22}{flag:>10}")

    conn.close()
    print("\n" + "=" * 66)
    print("Report complete.")
    print("=" * 66)


if __name__ == "__main__":
    main()