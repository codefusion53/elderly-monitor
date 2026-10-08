"""
Phase 4 - minimal Pulsar connection test (tuya-connector-python).

Goal: prove we can connect to the Tuya Message Service and receive ONE real
device event, before building the full production consumer. Run it, then use
or toggle a plug so Tuya pushes an event.

The tuya-connector-python SDK handles the Pulsar connection AND the payload
decryption internally, so we just print what arrives.

Setup (one time):
  pip install tuya-connector-python

Run (reads .env for TUYA_ACCESS_ID / TUYA_ACCESS_SECRET / TUYA_REGION):
  python -m collector.pulsar_test
"""
from __future__ import annotations

import json
import logging

from . import config

log = logging.getLogger("pulsar_test")

# tuya-connector-python uses the WSS endpoint (port 8285), not pulsar+ssl:7285.
MQ_ENDPOINTS = {
    "eu": "wss://mqe.tuyaeu.com:8285/",
    "us": "wss://mqe.tuyaus.com:8285/",
    "cn": "wss://mqe.tuyacn.com:8285/",
}


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    region = config.TUYA_REGION.split("-")[0]
    mq = MQ_ENDPOINTS.get(region, MQ_ENDPOINTS["eu"])

    try:
        from tuya_connector import TuyaOpenPulsar, TuyaCloudPulsarTopic
    except ImportError:
        log.error("tuya-connector-python not installed. Run: pip install tuya-connector-python")
        return

    log.info("Connecting to Tuya Message Queue: %s", mq)

    def on_message(msg):
        # The SDK delivers the decrypted message as a JSON string / dict.
        try:
            data = json.loads(msg) if isinstance(msg, (str, bytes)) else msg
        except Exception:
            data = msg
        log.info("EVENT RECEIVED: %s", data)
        # Tuya's decrypted event carries devId + status (the data points).
        if isinstance(data, dict):
            inner = data.get("data") or data
            if isinstance(inner, dict):
                log.info("  devId=%s  status=%s",
                         inner.get("devId"), inner.get("status"))

    pulsar = TuyaOpenPulsar(
        config.TUYA_ACCESS_ID, config.TUYA_ACCESS_SECRET, mq,
        TuyaCloudPulsarTopic.PROD,
    )
    pulsar.add_message_listener(on_message)
    log.info("Listening... now use/toggle a plug so Tuya pushes an event. "
             "Ctrl-C to stop.")
    pulsar.start()
    try:
        input()  # keep running until Enter/Ctrl-C
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        pulsar.stop()
        log.info("Stopped.")


if __name__ == "__main__":
    main()
