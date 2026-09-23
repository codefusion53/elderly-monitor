"""Thin wrapper around tinytuya.Cloud.

tinytuya handles token acquisition, refresh and request signing, which we
already proved working end-to-end during setup. This wrapper adds:
  - unit conversion (Tuya reports tenths of W / tenths of V)
  - the explicit online flag (the device-list endpoint returns None for it,
    so we fetch it from the device detail endpoint)
  - a single normalized dict per device poll

API-call optimisation:
  Each poll normally makes TWO Tuya calls: getstatus (power) plus a device
  detail call (the authoritative online flag). To stay within Tuya's free
  monthly quota, the online flag is fetched only every N cycles
  (ONLINE_CHECK_EVERY); in between, the last known online value is reused.
  The power reading still happens every cycle, so activity detection is
  unaffected. This roughly halves the API calls.
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
        # remember the last known online flag per device between cycles
        self._last_online: dict[str, bool | None] = {}

    def poll_device(self, tuya_device_id: str, fetch_online: bool = True) -> dict | None:
        """Return normalized telemetry for one device, or None on failure.

        fetch_online=False skips the extra device-detail call and reuses the
        last known online value (used on most cycles to save API quota).

        Normalized keys: cur_power_w, cur_current_ma, cur_voltage_v,
        add_ele_raw, switch_on, online.
        """
        try:
            status = self._cloud.getstatus(tuya_device_id)
        except Exception as e:  # network hiccup, token error, etc.
            log.warning("Poll failed for %s: %s", tuya_device_id, e)
            return None

        if not isinstance(status, dict) or not status.get("success", False):
            log.warning("Bad status response for %s: %s", tuya_device_id, status)
            return None

        points = {p["code"]: p["value"] for p in status.get("result", [])}

        # online flag: fetch fresh only when asked; otherwise reuse last known
        if fetch_online:
            online = None
            try:
                detail = self._cloud.cloudrequest(f"/v1.0/devices/{tuya_device_id}")
                if isinstance(detail, dict) and detail.get("success"):
                    online = detail.get("result", {}).get("online")
            except Exception as e:
                log.warning("Online check failed for %s: %s", tuya_device_id, e)
                online = self._last_online.get(tuya_device_id)
            self._last_online[tuya_device_id] = online
        else:
            online = self._last_online.get(tuya_device_id)

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
