"""
Tuya API connection test - Elderly Monitoring Project
Credentials are read from the .env file (same one the collector uses).

Setup (one time):
  pip install tinytuya python-dotenv
  cp .env.example .env   # and fill in the real values

Run (from the project root, next to .env):
  python tuya_connection_test.py
"""

import os
import sys

import tinytuya
from dotenv import load_dotenv

load_dotenv()

API_REGION = os.getenv("TUYA_REGION", "eu")
ACCESS_ID = os.getenv("TUYA_ACCESS_ID")
ACCESS_SECRET = os.getenv("TUYA_ACCESS_SECRET")

if not ACCESS_ID or not ACCESS_SECRET:
    sys.exit(
        "Missing TUYA_ACCESS_ID / TUYA_ACCESS_SECRET.\n"
        "Create a .env file (see .env.example) in the directory you run from."
    )

# Data point codes that prove the plug has energy monitoring
POWER_CODES = {
    "cur_power":   "Current power draw (tenths of a watt: 15234 = 1523.4 W)",
    "cur_current": "Current (mA)",
    "cur_voltage": "Voltage (tenths of a volt: 2301 = 230.1 V)",
    "add_ele":     "Accumulated energy increment (used for kWh totals)",
}


def main():
    print("=" * 60)
    print(f"STEP 1: Authenticating with Tuya Cloud (region: {API_REGION})...")
    print("=" * 60)
    cloud = tinytuya.Cloud(
        apiRegion=API_REGION,
        apiKey=ACCESS_ID,
        apiSecret=ACCESS_SECRET,
    )

    print("\n" + "=" * 60)
    print("STEP 2: Fetching device list...")
    print("=" * 60)
    devices = cloud.getdevices()

    if isinstance(devices, dict) and devices.get("Error"):
        print("\n[FAIL] Could not fetch devices:")
        print(devices)
        print("\nMost likely causes:")
        print(" - 'clientId is invalid' (2009) -> Access ID typo or wrong DC;")
        print("                                   run tuya_region_sweep.py")
        print(" - 'sign invalid'               -> Access Secret typo")
        print(" - 'permission deny' / 1106     -> API service not authorized")
        return

    if not devices:
        print("\n[PARTIAL] Authentication WORKED, but zero devices found.")
        print("=> The app-account link is missing or points elsewhere.")
        print("   Project > Devices > Link Tuya App Account > Add App Account")
        return

    print(f"\n[OK] Found {len(devices)} device(s):\n")
    for d in devices:
        print(f"  - {d.get('name')}  (id: {d.get('id')})  online: {d.get('online')}")

    print("\n" + "=" * 60)
    print("STEP 3: Reading live status of each device...")
    print("=" * 60)
    for d in devices:
        dev_id = d.get("id")
        print(f"\nDevice: {d.get('name')}  ({dev_id})")
        status = cloud.getstatus(dev_id)
        points = status.get("result", []) if isinstance(status, dict) else []

        if not points:
            print("  [WARN] No status returned:", status)
            continue

        found_power = False
        for p in points:
            code, value = p.get("code"), p.get("value")
            if code in POWER_CODES:
                found_power = True
                print(f"  [ENERGY] {code} = {value}   <- {POWER_CODES[code]}")
            else:
                print(f"           {code} = {value}")

        if found_power:
            print("  [OK] This plug HAS energy monitoring. We're in business!")
        else:
            print("  [FAIL] No energy data points found on this plug.")
            print("         It may be a switch-only model, or metering DPs are")
            print("         hidden - check the device debug page in Tuya IoT.")

    print("\n" + "=" * 60)
    print("Test complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()