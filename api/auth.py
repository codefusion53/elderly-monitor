"""
Phase 3 - Authentication and roles.

Session-based auth with bcrypt password hashing. Two roles:
  admin     - manages users, plugs, and per-residence settings; sees all.
  caregiver - scoped to one residence; sees the semaforo dashboard only.

Sessions are server-side (sessions table), so they can be revoked. Kept
deliberately simple and appropriate for this scale (no OAuth/JWT).
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import bcrypt

from interface.data_access import connect

SESSION_HOURS = 24 * 7  # a week


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def create_user(username: str, password: str, role: str = "caregiver",
                residence_id: int | None = None, display_name: str | None = None):
    conn = connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO users (username, password_hash, role, residence_id, display_name)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (username, hash_password(password), role, residence_id,
                 display_name or username),
            )
            return cur.fetchone()[0]
    finally:
        conn.close()


def authenticate(username: str, password: str) -> str | None:
    """Return a new session token on success, else None."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, password_hash FROM users WHERE username=%s",
                        (username,))
            row = cur.fetchone()
            if not row or not verify_password(password, row[1]):
                return None
            token = secrets.token_urlsafe(32)
            cur.execute(
                """INSERT INTO sessions (token, user_id, expires_at)
                   VALUES (%s, %s, %s)""",
                (token, row[0], datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)),
            )
            conn.commit()
            return token
    finally:
        conn.close()


def user_for_token(token: str | None):
    """Return dict(user) for a valid, unexpired session token, else None."""
    if not token:
        return None
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT u.id, u.username, u.role, u.residence_id, u.display_name
                   FROM sessions s JOIN users u ON u.id = s.user_id
                   WHERE s.token=%s AND s.expires_at > now()""",
                (token,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {"id": row[0], "username": row[1], "role": row[2],
                    "residence_id": row[3], "display_name": row[4]}
    finally:
        conn.close()


def logout(token: str):
    conn = connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM sessions WHERE token=%s", (token,))
    finally:
        conn.close()


def get_settings(residence_id: int) -> dict:
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT yellow_fraction, offline_tolerance_min, stale_after_min,
                          ceiling_override_min, extended_offline_min,
                          total_offline_critical_min
                   FROM residence_settings WHERE residence_id=%s""",
                (residence_id,),
            )
            row = cur.fetchone()
            if not row:
                return {"yellow_fraction": 0.75, "offline_tolerance_min": 20,
                        "stale_after_min": 10, "ceiling_override_min": None,
                        "extended_offline_min": 180,
                        "total_offline_critical_min": 40}
            return {"yellow_fraction": float(row[0]), "offline_tolerance_min": row[1],
                    "stale_after_min": row[2], "ceiling_override_min": row[3],
                    "extended_offline_min": row[4],
                    "total_offline_critical_min": row[5]}
    finally:
        conn.close()


def update_settings(residence_id: int, **fields):
    allowed = {"yellow_fraction", "offline_tolerance_min", "stale_after_min",
               "ceiling_override_min", "extended_offline_min",
               "total_offline_critical_min"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return
    cols = ", ".join(f"{k}=%s" for k in sets)
    conn = connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                f"UPDATE residence_settings SET {cols}, updated_at=now() WHERE residence_id=%s",
                (*sets.values(), residence_id),
            )
    finally:
        conn.close()
