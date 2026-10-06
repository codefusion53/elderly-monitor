#!/usr/bin/env python3

import os
import sys
import tinytuya
from dotenv import load_dotenv

load_dotenv()

API_REGION = os.getenv("TUYA_REGION", "eu")
API_KEY = os.getenv("TUYA_ACCESS_ID")
API_SECRET = os.getenv("TUYA_ACCESS_SECRET")

if not API_KEY or not API_SECRET:
    print("ERROR: TUYA_ACCESS_ID and TUYA_ACCESS_SECRET are not set in .env")
    sys.exit(1)


def main():
    if len(sys.argv) != 3:
        print("Usage:")
        print("  python tuya_command_test.py <DEVICE_ID> on")
        print("  python tuya_command_test.py <DEVICE_ID> off")
        sys.exit(1)

    device_id = sys.argv[1]
    action = sys.argv[2].lower()

    if action not in ("on", "off"):
        print("ERROR: action must be 'on' or 'off'")
        sys.exit(1)

    value = action == "on"

    cloud = tinytuya.Cloud(
        apiRegion=API_REGION,
        apiKey=API_KEY,
        apiSecret=API_SECRET,
    )

    print(f"Sending {action.upper()} command to {device_id}...")

    response = cloud.sendcommand(
        device_id,
        {
            "commands": [
                {
                    "code": "switch_1",
                    "value": value,
                }
            ]
        },
    )

    print("Tuya response:")
    print(response)

    if response.get("success"):
        print(f"\nSUCCESS: device turned {action.upper()}.")
    else:
        print("\nFAILED: Tuya did not accept the command.")
        sys.exit(1)


if __name__ == "__main__":
    main()