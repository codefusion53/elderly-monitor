"""Configuration loaded from environment variables (see .env.example)."""

import os

from dotenv import load_dotenv

load_dotenv()

# --- Tuya ---
TUYA_REGION = os.getenv("TUYA_REGION", "eu")
TUYA_ACCESS_ID = os.environ["TUYA_ACCESS_ID"]
TUYA_ACCESS_SECRET = os.environ["TUYA_ACCESS_SECRET"]

# --- Database ---
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://monitor:monitor@localhost:5432/monitor"
)

# --- Collector behaviour ---
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))

# A device is offline_confirmed only after this many minutes without a
# successful poll AND/OR online=false. This is the tolerance window
# promised to the client (Wi-Fi flickers must not trigger anything).
OFFLINE_TOLERANCE_MINUTES = int(os.getenv("OFFLINE_TOLERANCE_MINUTES", "20"))
