"""Thin wrapper around tinytuya.Cloud.

tinytuya handles token acquisition, refresh and request signing, which we
already proved working end-to-end during setup. This wrapper adds:
  - unit conversion (Tuya reports tenths of W / tenths of V)
  - the explicit online flag (the device-list endpoint returns None for it,
    so we fetch it from the device detail endpoint)
  - a single normalized dict per device poll
"""

import logging

import tinytuya

from . import config

log = logging.getLogger(__name__)


class TuyaClient:
    def __init__(self):
        self._cloud = tinytuya.Cloud(
            apiRegion=config.TUYA_REGION,
            apiKey=config.TUYA_ACCESS_ID,
            apiSecret=config.TUYA_ACCESS_SECRET,
        )

    def poll_device(self, tuya_device_id: str) -> dict | None:
        """Return normalized telemetry for one device, or None on failure.

        Normalized keys: cur_power_w, cur_current_ma, cur_voltage_v,
        add_ele_raw, switch_on, online.
        """
        try:
            status = self._cloud.getstatus(tuya_device_id)
            detail = self._cloud.cloudrequest(f"/v1.0/devices/{tuya_device_id}")
        except Exception as e:  # network hiccup, token error, etc.
            log.warning("Poll failed for %s: %s", tuya_device_id, e)
            return None

        if not isinstance(status, dict) or not status.get("success", False):
            log.warning("Bad status response for %s: %s", tuya_device_id, status)
            return None

        points = {p["code"]: p["value"] for p in status.get("result", [])}

        online = None
        if isinstance(detail, dict) and detail.get("success"):
            online = detail.get("result", {}).get("online")

        return {
            "cur_power_w": _scale(points.get("cur_power"), 0.1),
            "cur_current_ma": points.get("cur_current"),
            "cur_voltage_v": _scale(points.get("cur_voltage"), 0.1),
            "add_ele_raw": points.get("add_ele"),
            "switch_on": points.get("switch_1"),
            "online": online,
        }


def _scale(value, factor):
    return None if value is None else round(value * factor, 2)
