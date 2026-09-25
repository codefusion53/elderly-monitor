"""
Tuya events consumer (Phase 4 - proof of concept).

Subscribes to Tuya's Message Service (Pulsar) and reacts to pushed device
events instead of polling. Writes to the SAME database via db.py, so the
inference, api and alerting layers are unchanged.

STATUS: proof of concept. It maps the three relevant event types to the
existing schema and reuses the connectivity state machine. To run for real it
needs:
  - Message Service enabled + authorised on the Tuya project;
  - the tuya-pulsar client installed (pip install tuya-pulsar), or the
    documented Pulsar client plus Tuya's AES payload decryption;
  - confirmation that message volume stays within the free tier.

Event types (Tuya):
  dp_report -> device reported data (power/switch)  => insert a reading
  online    -> device online                        => connectivity
  offline   -> device offline                       => connectivity

Run (once Message Service is enabled):
  python -m collector.events
"""
from __future__ import annotations

import json
import logging

from . import config, connectivity, db

log = logging.getLogger("collector.events")

# EU Pulsar endpoint (mirror of TUYA_REGION); swap for us/cn if region changes.
PULSAR_URLS = {
    "eu": "pulsar+ssl://mqe.tuyaeu.com:7285/",
    "us": "pulsar+ssl://mqe.tuyaus.com:7285/",
    "cn": "pulsar+ssl://mqe.tuyacn.com:7285/",
}


def _scale(value, factor):
    return None if value is None else round(value * factor, 2)


def _reading_from_status(status_list):
    """Turn a dp_report 'status' list into our normalized reading dict,
    using the SAME unit conversions as the poller (tuya_client)."""
    points = {p.get("code"): p.get("value") for p in (status_list or [])}
    return {
        "cur_power_w": _scale(points.get("cur_power"), 0.1),
        "cur_current_ma": points.get("cur_current"),
        "cur_voltage_v": _scale(points.get("cur_voltage"), 0.1),
        "add_ele_raw": points.get("add_ele"),
        "switch_on": points.get("switch_1"),
        "online": True,   # a device reporting data is, by definition, online
    }


def _device_by_tuya_id(conn, tuya_id):
    for d in db.fetch_devices(conn):
        if d["tuya_device_id"] == tuya_id:
            return d
    return None


def handle_event(conn, event: dict):
    """Process one decoded Tuya event. `event` is the plaintext JSON dict.

    Expected shape (varies slightly by Tuya version):
      {"devId": "...", "bizCode"/"eventType": "dp_report"/"online"/"offline",
       "status": [ {code, value}, ... ]  # for dp_report
      }
    """
    tuya_id = event.get("devId") or event.get("dev_id")
    etype = event.get("bizCode") or event.get("eventType") or event.get("event_type")
    if not tuya_id:
        log.warning("event without device id: %s", event)
        return

    device = _device_by_tuya_id(conn, tuya_id)
    if not device:
        log.warning("event for unknown device %s (ignored)", tuya_id)
        return

    if etype in ("dp_report", "statusReport", "dpReport"):
        reading = _reading_from_status(event.get("status") or event.get("data"))
        db.insert_reading(conn, device["id"], reading)
        connectivity.on_poll_result(conn, device, poll_ok=True, reported_online=True)
        log.info("dp_report %s: %s W", device["name"], reading["cur_power_w"])
    elif etype in ("online",):
        connectivity.on_poll_result(conn, device, poll_ok=True, reported_online=True)
        log.info("online %s", device["name"])
    elif etype in ("offline",):
        connectivity.on_poll_result(conn, device, poll_ok=False, reported_online=False)
        log.info("offline %s", device["name"])
    else:
        log.debug("ignoring event type %s for %s", etype, device["name"])


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    region = config.TUYA_REGION.split("-")[0]  # eu-w -> eu
    url = PULSAR_URLS.get(region, PULSAR_URLS["eu"])
    log.info("Events consumer starting (region=%s, url=%s)", region, url)

    try:
        import tuya_pulsar  # type: ignore
    except ImportError:
        log.error("tuya-pulsar not installed. This is the proof-of-concept "
                  "entry point; install the Tuya Pulsar client and wire the "
                  "subscription here once Message Service is enabled.")
        log.error("Design and event handling are ready in handle_event(); the "
                  "remaining work is the Pulsar connection + AES decrypt + "
                  "reconnect loop, which is the funded Phase 4 task.")
        return

    # --- Pulsar subscription wiring (completed in the funded migration) ---
    # conn = db.get_conn()
    # client = tuya_pulsar.TuyaPulsar(config.TUYA_ACCESS_ID,
    #                                 config.TUYA_ACCESS_SECRET, url)
    # def on_message(msg):
    #     event = tuya_pulsar.decrypt(msg, config.TUYA_ACCESS_SECRET)
    #     handle_event(conn, json.loads(event))
    #     client.ack(msg)          # ack only after successful DB write
    # client.add_message_listener(on_message)
    # client.run()  # with reconnect handling


if __name__ == "__main__":
    main()
