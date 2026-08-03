"""
Tuya raw token test - tries EVERY regional endpoint with pure HTTP.
Credentials are read from the .env file (same one the collector uses).
No tinytuya involved, so we see Tuya's exact response per region.

Setup (one time):
  pip install requests python-dotenv
  cp .env.example .env   # and fill in the real values

Run (from the project root, next to .env):
  python tuya_region_sweep.py
"""

import hashlib
import hmac
import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

ACCESS_ID = os.getenv("TUYA_ACCESS_ID")
ACCESS_SECRET = os.getenv("TUYA_ACCESS_SECRET")

if not ACCESS_ID or not ACCESS_SECRET:
    sys.exit(
        "Missing TUYA_ACCESS_ID / TUYA_ACCESS_SECRET.\n"
        "Create a .env file (see .env.example) in the directory you run from."
    )

ENDPOINTS = {
    "Central Europe":  "https://openapi.tuyaeu.com",
    "Western Europe":  "https://openapi-weaz.tuyaeu.com",
    "Western America": "https://openapi.tuyaus.com",
    "Eastern America": "https://openapi-ueaz.tuyaus.com",
    "India":           "https://openapi.tuyain.com",
    "China":           "https://openapi.tuyacn.com",
}


def sign_request(client_id, secret, t, path):
    # Tuya v2 signature for a GET token request with empty body
    empty_body_sha256 = hashlib.sha256(b"").hexdigest()
    string_to_sign = "GET\n" + empty_body_sha256 + "\n\n" + path
    message = client_id + t + string_to_sign
    return (
        hmac.new(secret.encode(), message.encode(), hashlib.sha256)
        .hexdigest()
        .upper()
    )


def try_endpoint(name, base):
    path = "/v1.0/token?grant_type=1"
    t = str(int(time.time() * 1000))
    headers = {
        "client_id": ACCESS_ID,
        "t": t,
        "sign_method": "HMAC-SHA256",
        "sign": sign_request(ACCESS_ID, ACCESS_SECRET, t, path),
    }
    try:
        r = requests.get(base + path, headers=headers, timeout=10)
        data = r.json()
    except Exception as e:
        print(f"{name:16s} -> network error: {e}")
        return

    if data.get("success"):
        print(f"{name:16s} -> SUCCESS! Token obtained. THIS is the data center.")
    else:
        print(f"{name:16s} -> code {data.get('code')}: {data.get('msg')}")


def main():
    print(f"Sweeping all Tuya data centers with Access ID {ACCESS_ID[:6]}... \n")
    for name, base in ENDPOINTS.items():
        try_endpoint(name, base)

    print("""
Interpretation:
  SUCCESS on one region      -> project alive on that DC. Set TUYA_REGION
                                accordingly in .env (eu, eu-w, us, us-e,
                                in, cn) and rerun the main test.
  code 2009/1005 everywhere  -> this Access ID exists on NO data center:
                                the project was deleted/recreated, or the
                                ID has a typo. Re-copy from the project's
                                Overview tab.
  code 1004 / sign invalid   -> ID exists but the secret is wrong
                                (regenerated). Re-copy the Access Secret.
""")


if __name__ == "__main__":
    main()