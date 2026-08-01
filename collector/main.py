"""Collector entry point.

Polls every device on a fixed interval, stores raw telemetry, and advances
the connectivity state machine. Designed to be boring and unkillable: any
exception is logged and the loop continues, because a collector that dies
silently at 2am is exactly the failure this product exists to prevent.

Run:  python -m collector.main
"""

import logging
import time

from . import config, connectivity, db
from .tuya_client import TuyaClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("collector")


def poll_all(conn, tuya: TuyaClient):
    for device in db.fetch_devices(conn):
        try:
            result = tuya.poll_device(device["tuya_device_id"])
            if result is not None:
                db.insert_reading(conn, device["id"], result)
                log.info(
                    "%s: %s W, switch=%s, online=%s",
                    device["name"],
                    result["cur_power_w"],
                    result["switch_on"],
                    result["online"],
                )
                connectivity.on_poll_result(
                    conn, device, poll_ok=True, reported_online=result["online"]
                )
            else:
                connectivity.on_poll_result(
                    conn, device, poll_ok=False, reported_online=None
                )
        except Exception:
            log.exception("Unexpected error polling %s", device["name"])
            try:
                connectivity.on_poll_result(
                    conn, device, poll_ok=False, reported_online=None
                )
            except Exception:
                log.exception("State machine error for %s", device["name"])


def main():
    log.info(
        "Collector starting: interval=%ss, offline tolerance=%s min",
        config.POLL_INTERVAL_SECONDS,
        config.OFFLINE_TOLERANCE_MINUTES,
    )
    tuya = TuyaClient()
    conn = db.get_conn()

    while True:
        started = time.monotonic()
        try:
            poll_all(conn, tuya)
        except Exception:
            log.exception("Top-level poll cycle error; reconnecting DB")
            try:
                conn.close()
            except Exception:
                pass
            time.sleep(5)
            conn = db.get_conn()

        elapsed = time.monotonic() - started
        time.sleep(max(1.0, config.POLL_INTERVAL_SECONDS - elapsed))


if __name__ == "__main__":
    main()
