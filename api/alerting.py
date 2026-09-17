"""
Phase 3 - Alerting engine (tiered).

Each cycle: compute current state, compare to last notified, and notify only
on CHANGE (never spams a stable state).

Tiering, confirmed with the client:
  ROUTINE  (activity YELLOW, or return-to-GREEN)          -> email, 'all' contacts.
  ADMIN    (a single plug offline, others still online)   -> email, admin/caregiver
           technical notice. Not an alarm about the person.
  CRITICAL (activity RED; OR all plugs offline; OR any plug
           offline beyond EXTENDED_OFFLINE_MIN)           -> WhatsApp + email, all.

The single-plug vs total/extended distinction is why this engine looks at
per-device connectivity, not only the residence rollup.

Run once:  python -m api.alerting
Loop:      python -m api.alerting --loop 300
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone

from interface.data_access import connect
from api.state_service import compute_all_states
from api.notify import send_email, send_whatsapp

# Thresholds (defaults; overridable per-residence via residence_settings).
# Client-confirmed tiering:
#   - a SINGLE plug offline escalates to critical only after EXTENDED_OFFLINE_MIN
#   - ALL plugs offline at once escalates to critical after the shorter
#     TOTAL_OFFLINE_CRITICAL_MIN, because a total outage likely means a general
#     power/Wi-Fi loss at the home and the caregiver should know quickly.
EXTENDED_OFFLINE_MIN = 180        # single plug offline this long -> critical
TOTAL_OFFLINE_CRITICAL_MIN = 40   # all plugs offline this long -> critical


def _residence_id(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM residences ORDER BY id LIMIT 1")
        r = cur.fetchone()
        return r[0] if r else 1


def _last(conn, rid):
    with conn.cursor() as cur:
        cur.execute("SELECT last_state FROM alert_state WHERE residence_id=%s", (rid,))
        r = cur.fetchone()
        return r[0] if r else None


def _remember(conn, rid, tag, category, notified):
    with conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO alert_state (residence_id,last_state,last_category,
                    last_changed_at,last_notified_at)
               VALUES (%s,%s,%s,now(),%s)
               ON CONFLICT (residence_id) DO UPDATE SET
                    last_state=EXCLUDED.last_state, last_category=EXCLUDED.last_category,
                    last_changed_at=now(),
                    last_notified_at=COALESCE(EXCLUDED.last_notified_at, alert_state.last_notified_at)""",
            (rid, tag, category, datetime.now(timezone.utc) if notified else None))


def _contacts(conn, rid, critical):
    with conn.cursor() as cur:
        if critical:
            cur.execute("""SELECT name,email,whatsapp,tier FROM alert_contacts
                           WHERE residence_id=%s AND active""", (rid,))
        else:
            cur.execute("""SELECT name,email,whatsapp,tier FROM alert_contacts
                           WHERE residence_id=%s AND active AND tier='all'""", (rid,))
        return cur.fetchall()


def _log(conn, rid, channel, to, tier, tag, subject, ok, detail):
    with conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO alert_log (residence_id,channel,to_addr,tier,state,subject,ok,detail)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (rid, channel, to, tier, tag, subject, ok, detail))


def _classify(data, thresholds=None):
    """Turn the computed state into an alert decision.

    thresholds: optional dict with 'extended_offline_min' and
    'total_offline_critical_min' (per-residence overrides).

    Returns (tag, level, subject, body) where:
      tag   - a stable string identifying the situation (for change detection)
      level - 'routine' | 'admin' | 'critical' | None (nothing worth sending)
    """
    thresholds = thresholds or {}
    extended_min = thresholds.get("extended_offline_min", EXTENDED_OFFLINE_MIN)
    total_min = thresholds.get("total_offline_critical_min", TOTAL_OFFLINE_CRITICAL_MIN)

    res = data["residence"]
    devices = data.get("devices", [])
    system = data.get("system", {})
    state = res["state"]

    # --- system / connectivity situations ---
    if state == "SYSTEM" or not system.get("ok", True):
        offline = [d for d in devices if d.get("conn_state") == "offline_confirmed"
                   or (d.get("state") == "RED" and d.get("category") == "system")]
        total = len(devices) or 1
        stale_min = system.get("stale_minutes") or 0
        all_down = len(offline) >= total

        # total outage: critical after the SHORT threshold (client requirement)
        if all_down and stale_min >= total_min:
            return ("SYS_CRITICAL", "critical",
                    "Alerta Zelo Smart: sistema sem monitorizacao",
                    "Todas as tomadas ficaram offline ao mesmo tempo "
                    f"(ha mais de {int(stale_min)} min).\n\nIsto indica provavelmente "
                    "um corte geral de energia ou de internet na casa. Convem contactar "
                    "ou verificar. (E uma falha tecnica, nao um sinal direto sobre a pessoa, "
                    "mas a monitorizacao esta indisponivel.)")
        # single plug offline for a long time: critical after the LONG threshold
        if (not all_down) and stale_min >= extended_min:
            which = ", ".join(d["device"] for d in offline) or "uma tomada"
            return ("SYS_CRITICAL", "critical",
                    "Alerta Zelo Smart: tomada offline ha muito tempo",
                    f"A tomada ({which}) esta offline ha mais de {int(stale_min//60)}h. "
                    "A monitorizacao dessa tomada esta indisponivel ha demasiado tempo; "
                    "convem verificar.")
        # otherwise: confirmed but recent -> discreet admin/technical email notice
        which = ", ".join(d["device"] for d in offline) or "uma tomada"
        return ("SYS_ADMIN", "admin",
                "Aviso tecnico Zelo Smart: tomada offline",
                f"A tomada ({which}) esta offline. Verifique o Wi-Fi/energia dessa "
                "tomada. As restantes continuam a comunicar, por isso a monitorizacao "
                "geral mantem-se; e apenas uma questao tecnica a resolver.")

    # --- activity situations ---
    if state == "RED":
        return ("ACT_RED", "critical",
                "Alerta Zelo Smart: possivel inatividade",
                f"O sistema detetou um desvio significativo da rotina habitual.\n\n"
                f"{res.get('reason','')}\n\nRecomenda-se verificar o bem-estar da pessoa.")
    if state == "YELLOW":
        return ("ACT_YELLOW", "routine",
                "Aviso Zelo Smart: sem atividade recente",
                f"{res.get('reason','')}\n\nAinda dentro do normal, mas a acompanhar.")
    if state == "GREEN":
        return ("GREEN", "recovered", "Zelo Smart: tudo normalizado",
                "A situacao regressou ao normal.")
    return ("UNKNOWN", None, "", "")


def run_once(verbose=True):
    conn = connect()
    try:
        rid = _residence_id(conn)
        data = compute_all_states()
        # per-residence alert thresholds (fall back to module defaults)
        thresholds = {}
        try:
            from api.auth import get_settings
            s = get_settings(rid)
            if s.get("extended_offline_min"):
                thresholds["extended_offline_min"] = s["extended_offline_min"]
            if s.get("total_offline_critical_min"):
                thresholds["total_offline_critical_min"] = s["total_offline_critical_min"]
        except Exception:
            pass
        tag, level, subject, body = _classify(data, thresholds)
        prev = _last(conn, rid)

        if verbose:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] tag={tag} level={level} prev={prev}")

        if tag == prev:
            return  # no change, no spam

        # a return to normal only notifies if we were previously in a bad state
        if level == "recovered":
            if prev in ("ACT_RED", "ACT_YELLOW", "SYS_ADMIN", "SYS_CRITICAL"):
                level = "routine"
            else:
                _remember(conn, rid, tag, "activity", notified=False)
                return

        if level is None:
            _remember(conn, rid, tag, "activity", notified=False)
            return

        critical = level == "critical"
        contacts = _contacts(conn, rid, critical)
        any_sent = False
        for name, email, whatsapp, tier in contacts:
            if critical and whatsapp:
                ok, detail = send_whatsapp(whatsapp, f"{subject}\n\n{body}")
                _log(conn, rid, "whatsapp", whatsapp, level, tag, subject, ok, detail)
                any_sent = any_sent or ok
            if email:
                ok, detail = send_email(email, subject, body)
                _log(conn, rid, "email", email, level, tag, subject, ok, detail)
                any_sent = any_sent or ok

        _remember(conn, rid, tag, "system" if tag.startswith("SYS") else "activity",
                  notified=any_sent)
        if verbose:
            print(f"  level={level} notified={any_sent} contacts={len(contacts)}")
    finally:
        conn.close()


def main():
    if "--loop" in sys.argv:
        i = sys.argv.index("--loop")
        interval = int(sys.argv[i+1]) if len(sys.argv) > i+1 else 300
        print(f"Alerting loop every {interval}s. Ctrl-C to stop.")
        while True:
            try:
                run_once()
            except Exception as e:
                print("cycle error:", e)
            time.sleep(interval)
    else:
        run_once()


if __name__ == "__main__":
    main()
