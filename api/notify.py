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
# Optional approved Content Template (required for business-initiated sends on
# many Twilio accounts). When set, we send the template instead of free Body.
WA_CONTENT_SID = os.getenv("WHATSAPP_CONTENT_SID")


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


def send_whatsapp(to_number: str, body: str,
                  content_variables: dict | None = None) -> tuple[bool, str]:
    if not (WA_API_URL and WA_API_TOKEN and WA_FROM):
        return False, "WhatsApp not configured"
    try:
        # Twilio Messages API: HTTP basic auth (AccountSID:AuthToken), form post
        # with the whatsapp: prefix on both From and To.
        auth = None
        headers = None
        if ":" in WA_API_TOKEN:
            sid, token = WA_API_TOKEN.split(":", 1)
            auth = (sid, token)
        else:
            headers = {"Authorization": f"Bearer {WA_API_TOKEN}"}
        data = {"From": f"whatsapp:{WA_FROM}", "To": f"whatsapp:{to_number}"}
        if WA_CONTENT_SID:
            # business-initiated send via an approved Content Template
            data["ContentSid"] = WA_CONTENT_SID
            if content_variables:
                import json as _json
                data["ContentVariables"] = _json.dumps(content_variables)
        else:
            # free-form text: only valid inside the 24h user-initiated window
            data["Body"] = body
        r = requests.post(
            WA_API_URL,
            auth=auth,
            headers=headers,
            data=data,
            timeout=15,
        )
        if 200 <= r.status_code < 300:
            return True, f"sent (http {r.status_code})"
        # surface Twilio's error message so failures are debuggable
        detail = ""
        try:
            j = r.json()
            detail = j.get("message") or j.get("detail") or ""
        except Exception:
            detail = r.text[:200]
        return False, f"http {r.status_code}: {detail}"
    except Exception as e:
        return False, f"whatsapp error: {e}"
