"""Database access layer (psycopg2). Small and explicit on purpose."""

import logging

import time

import psycopg2
import psycopg2.extras

from . import config

log = logging.getLogger(__name__)


def get_conn(retries: int = 30, delay: float = 2.0):
    """Connect to Postgres, retrying while the DB container starts up."""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            conn = psycopg2.connect(config.DATABASE_URL)
            conn.autocommit = True
            if attempt > 1:
                log.info("Database connected after %s attempts", attempt)
            return conn
        except psycopg2.OperationalError as e:
            if "password authentication failed" in str(e):
                raise  # config problem: retrying will never help, fail loud
            last_err = e
            log.info("Database not ready (attempt %s/%s), retrying...", attempt, retries)
            time.sleep(delay)
    raise last_err


def fetch_devices(conn):
    """All devices with their live connectivity state."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """SELECT id, tuya_device_id, name, conn_state,
                      conn_state_since, last_successful_poll
               FROM devices ORDER BY id"""
        )
        return cur.fetchall()


def insert_reading(conn, device_id: int, r: dict):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO readings
               (device_id, cur_power_w, cur_current_ma, cur_voltage_v,
                add_ele_raw, switch_on, online)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                device_id,
                r["cur_power_w"],
                r["cur_current_ma"],
                r["cur_voltage_v"],
                r["add_ele_raw"],
                r["switch_on"],
                r["online"],
            ),
        )
        # add_ele is an INCREMENT counter, not a running total:
        # accumulate it on our side.
        if r["add_ele_raw"]:
            cur.execute(
                "UPDATE devices SET total_ele_wh = total_ele_wh + %s WHERE id = %s",
                (r["add_ele_raw"], device_id),
            )


def mark_poll_success(conn, device_id: int):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE devices SET last_successful_poll = now() WHERE id = %s",
            (device_id,),
        )


def set_conn_state(conn, device_id: int, state: str):
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE devices
               SET conn_state = %s, conn_state_since = now()
               WHERE id = %s""",
            (state, device_id),
        )


def insert_connectivity_event(conn, device_id: int, event_type: str, detail: str):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO connectivity_events (device_id, event_type, detail)
               VALUES (%s, %s, %s)""",
            (device_id, event_type, detail),
        )
    log.info("Connectivity event for device %s: %s (%s)", device_id, event_type, detail)
