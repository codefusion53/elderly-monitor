"""
Phase 3 - Notification channels.

Two channels, pluggable:
  email    - via SMTP (works immediately, free; used for routine + all tiers)
  whatsapp - via the WhatsApp Business API (Twilio-style HTTP); used for
             critical alerts once the client's Business account is set up.

Both are wrapped so a missing/unconfigured channel fails safely (logs and
returns False) rather than crashing the alert loop. Config comes from .env.
"""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage

import requests

# ---- email (SMTP) ----
def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip().strip('"').strip("'")
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = _int_env("SMTP_PORT", 587)
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "alertas@zelosmart.local")

# ---- whatsapp (Twilio-style; swap for Meta if preferred) ----
WA_API_URL = os.getenv("WHATSAPP_API_URL")      # provider endpoint
WA_API_TOKEN = os.getenv("WHATSAPP_API_TOKEN")
WA_FROM = os.getenv("WHATSAPP_FROM")            # sender number/id


def send_email(to_addr: str, subject: str, body: str) -> tuple[bool, str]:
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS):
        return False, "SMTP not configured"
    try:
        msg = EmailMessage()
        msg["From"] = SMTP_FROM
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.set_content(body)
        ctx = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls(context=ctx)
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
        return True, "sent"
    except Exception as e:
        return False, f"email error: {e}"


def send_whatsapp(to_number: str, body: str) -> tuple[bool, str]:
    if not (WA_API_URL and WA_API_TOKEN and WA_FROM):
        return False, "WhatsApp not configured"
    try:
        # Twilio-style form post; adjust to the chosen provider's contract.
        r = requests.post(
            WA_API_URL,
            auth=(WA_API_TOKEN.split(":")[0], WA_API_TOKEN.split(":")[-1])
                 if ":" in WA_API_TOKEN else None,
            data={"From": f"whatsapp:{WA_FROM}",
                  "To": f"whatsapp:{to_number}", "Body": body},
            headers=None if ":" in WA_API_TOKEN
                    else {"Authorization": f"Bearer {WA_API_TOKEN}"},
            timeout=15,
        )
        ok = 200 <= r.status_code < 300
        return ok, f"http {r.status_code}"
    except Exception as e:
        return False, f"whatsapp error: {e}"
