"""Shared read-only data access for interface/reporting scripts.

Loads readings and the current live state from the collector's database.
Kept separate so every interface tool uses one consistent query path.
"""
from __future__ import annotations

import os

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

from inference.baseline import Reading

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://monitor:monitor@localhost:5432/monitor"
)
TZ = os.getenv("CHART_TZ", "Europe/Lisbon")


def connect():
    return psycopg2.connect(DATABASE_URL)


def device_names(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM devices ORDER BY id")
        return [r[0] for r in cur.fetchall()]


def load_readings(conn, device_name: str, tz: str = TZ) -> list[Reading]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT (r.ts AT TIME ZONE %s) AS local_ts,
                   COALESCE(r.cur_power_w, 0), COALESCE(r.online, true)
            FROM readings r JOIN devices d ON d.id = r.device_id
            WHERE d.name = %s
            ORDER BY r.ts
            """,
            (tz, device_name),
        )
        return [
            Reading(ts=ts, device=device_name, power_w=float(p), online=bool(o))
            for ts, p, o in cur.fetchall()
        ]


def live_state_rows(conn):
    """Current connectivity state per device (for a status view)."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """SELECT name, conn_state, conn_state_since, last_successful_poll,
                      total_ele_wh
               FROM devices ORDER BY id"""
        )
        return cur.fetchall()
