# Zelo Smart — Installation & Deployment Guide

End-to-end guide to deploy the elderly-monitoring system on a Linux VPS:
the Docker application stack, the nginx reverse proxy, the domain and HTTPS,
and the public installation page. Written for Ubuntu/Debian; adjust package
commands for other distributions.

Current production host: Hostinger KVM VPS, nginx on port 80/443 in front of
the Docker stack, app reachable at `127.0.0.1:8000`, domain `zelosmart.tech`.

---

## 1. Prerequisites

- A VPS with a public IP, root (or sudo) SSH access, Ubuntu 22.04+.
- A domain pointed, or pointable, at the VPS (here `zelosmart.tech`).
- Docker Engine + Docker Compose V2 (`docker compose`, with a space).
- Tuya IoT project credentials (Access ID + Secret), region, and the plugs
  linked to the project's app account.
- An SMTP account for email alerts (Brevo relay in production).
- (Optional, for WhatsApp) a production Twilio account with a Meta-approved
  message template.

Install Docker + Compose V2 if needed:
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo systemctl enable --now docker          # start now + on every boot
docker compose version                       # confirm V2 is available
```

---

## 2. Get the code

```bash
sudo mkdir -p /opt && cd /opt
git clone <your-repo-url> elderly-monitor    # or upload/unzip the project
cd elderly-monitor
```

Keep the project in a fixed path (e.g. `/opt/elderly-monitor`). All commands
below run from that directory.

---

## 3. Configure the environment

```bash
cp .env.example .env
nano .env
```

Fill in every value. `.env` is git-ignored and must never be committed.

| Key | What it is |
|---|---|
| `TUYA_REGION` | Tuya data center (`eu`, `us`, …) |
| `TUYA_ACCESS_ID`, `TUYA_ACCESS_SECRET` | Tuya IoT project credentials |
| `DB_PASSWORD` | Postgres password (used by compose; pick a strong one) |
| `DATABASE_URL` | `postgresql://monitor:<DB_PASSWORD>@db:5432/monitor` |
| `POLL_INTERVAL_SECONDS` | collector poll interval (default 60) |
| `OFFLINE_TOLERANCE_MINUTES` | offline-confirm window (default 20) |
| `ONLINE_CHECK_EVERY` | fetch online flag every Nth cycle (default 5) |
| `CHART_TZ` | timezone for charts/report (default Europe/Lisbon) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` | email alerts |
| `WHATSAPP_API_URL`, `WHATSAPP_API_TOKEN`, `WHATSAPP_FROM`, `WHATSAPP_CONTENT_SID` | WhatsApp alerts |

Values are read literally — no quotes, no trailing spaces.

> **Email deliverability:** Gmail SMTP delivers to Gmail but is silently
> dropped by some providers (e.g. Hotmail). Use the Brevo relay
> (`SMTP_HOST=smtp-relay.brevo.com`) in production.

---

## 4. First start

```bash
docker compose up -d --build
```

On a **fresh** database the full `schema.sql` is applied automatically the
first time the volume is created — nothing to run. On an **existing** database
that predates the alert-threshold columns, run the idempotent migration once:

```bash
docker compose exec -T db psql -U monitor -d monitor -c \
"ALTER TABLE residence_settings \
 ADD COLUMN IF NOT EXISTS extended_offline_min INTEGER NOT NULL DEFAULT 180, \
 ADD COLUMN IF NOT EXISTS total_offline_critical_min INTEGER NOT NULL DEFAULT 40;"
```

Create the first admin user:
```bash
docker compose exec web python -c \
"from api.auth import create_user; create_user('admin','PICK_A_PASSWORD',role='admin')"
```

---

## 5. Verify the stack

```bash
docker compose ps                          # db, collector, web, alerting all "Up"
curl -s localhost:8000/api/health          # -> {"ok":true}
docker compose logs -f collector           # watch a poll cycle (Ctrl-C to exit)
```

In the database, confirm readings are flowing:
```sql
SELECT count(*), min(ts), max(ts) FROM readings;   -- max(ts) within ~2 min
```

The app is bound to `127.0.0.1:8000` — not publicly reachable yet. nginx makes
it public over HTTPS in the next steps.

---

## 6. Point the domain at the VPS (DNS)

In the domain's DNS panel (Hostinger hPanel → Domains → DNS), set:

| Type | Name | Value |
|---|---|---|
| A | `@`   | `<VPS_IP>` |
| A | `www` | `<VPS_IP>` |

Wait until it resolves before requesting a certificate:
```bash
dig +short zelosmart.tech
dig +short www.zelosmart.tech       # both must return <VPS_IP>
```

---

## 7. nginx reverse proxy

nginx terminates HTTP(S) on the host and proxies to the app container. Create a
server block for the domain:

```bash
sudo tee /etc/nginx/sites-available/zelosmart >/dev/null <<'EOF'
server {
    listen 80;
    listen [::]:80;
    server_name zelosmart.tech www.zelosmart.tech;

    # Public static installation page (self-contained; independent of the app)
    location = /instalar  { alias /var/www/zelosmart/instalar/index.html; default_type text/html; }
    location = /instalar/ { alias /var/www/zelosmart/instalar/index.html; default_type text/html; }

    # Everything else -> the monitoring app
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
sudo ln -s /etc/nginx/sites-available/zelosmart /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx     # reload is graceful (no downtime)
```

nginx routes by hostname, so requests by raw IP keep hitting any pre-existing
default block and the monitoring app is untouched.

---

## 8. HTTPS (Let's Encrypt)

Only after DNS resolves to the VPS:

```bash
sudo apt update && sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d zelosmart.tech -d www.zelosmart.tech
```

certbot adds the `443` server block and an automatic `http → https` redirect,
and installs a renewal timer. Confirm renewal works:

```bash
sudo certbot renew --dry-run
sudo systemctl status certbot.timer --no-pager    # should be active
```

> The certificate must keep renewing: if it lapses, HTTPS breaks and any
> printed QR code that points to the domain stops working.

---

## 9. Public installation page (`/instalar`)

The customer pairing guide is a single self-contained HTML file (CSS inline,
logo embedded as a data URI) — one request, no external asset that can fail.

```bash
sudo mkdir -p /var/www/zelosmart/instalar
# upload the file, then:
sudo mv /tmp/instalar.html /var/www/zelosmart/instalar/index.html
sudo chown -R www-data:www-data /var/www/zelosmart
```

Transfer the file with `scp` (not a terminal paste): the embedded logo is one
long line that a paste can truncate.
```bash
# from your machine:
scp instalar.html root@<VPS_IP>:/tmp/instalar.html
```

Verify it is intact and the logo is embedded:
```bash
grep -c "data:image/png;base64" /var/www/zelosmart/instalar/index.html   # 1
wc -c /var/www/zelosmart/instalar/index.html                             # ~27500
```

Test every URL variant lands 200 over HTTPS before encoding the QR:
```bash
for u in http://zelosmart.tech/instalar https://zelosmart.tech/instalar \
         https://www.zelosmart.tech/instalar https://zelosmart.tech/instalar/ ; do
  curl -sS -o /dev/null -w "%{http_code}  ->  %{url_effective}\n" -L "$u"
done
```
Then open `https://zelosmart.tech/instalar` on a real phone over cellular data.
Only after that passes, generate the QR for `https://zelosmart.tech/instalar`.

---

## 10. External uptime monitoring (recommended)

A server cannot alert you that it is down. Add an external monitor so a total
VPS/stack outage still reaches you:

1. Create a free account at uptimerobot.com (or healthchecks.io).
2. Add an HTTP(s) monitor for `https://zelosmart.tech/api/health` (returns
   `{"ok":true}`), interval 5 minutes.
3. Set the alert contact (email, and optionally the mobile app).

This closes the one reliability gap the in-app alerting cannot cover.

---

## 11. Operations

- **Reboot resilience:** all four services use `restart: unless-stopped`, and
  Docker is enabled on boot (`systemctl is-enabled docker` → `enabled`), so the
  stack returns automatically after a reboot. Confirm: reboot, then
  `docker compose ps` shows all four `Up`.
- **Config change** (`.env` / compose): `docker compose down && docker compose up -d`
  (recreate, not restart). `down` keeps data; only `down -v` deletes the volume.
- **Code change:** `docker compose up -d --build`.
- **Logs:** `docker compose logs -f collector` (or `web`, `alerting`, `db`).
- **Backups:** daily `pg_dump | gzip` off-box, with periodic restore tests:
  ```bash
  docker compose exec -T db pg_dump -U monitor monitor | gzip > backup_$(date +%F).sql.gz
  ```
- **Updating the install page** later: replace
  `/var/www/zelosmart/instalar/index.html` (scp + the two verify commands). The
  URL and QR never change, so no reprint is needed.

---

## 12. Security checklist (before launch)

- [ ] Postgres bound to localhost only — `ss -tlnp | grep 5432` shows
      `127.0.0.1:5432`, never `0.0.0.0:5432`.
- [ ] HTTPS active and auto-renewing (`certbot renew --dry-run` clean).
- [ ] Admin password is strong and unique; `.env` not committed.
- [ ] **Rotate every credential shared over chat during setup** — VPS root/SSH,
      Tuya Access ID/Secret, Twilio token, Brevo key, DB password.
- [ ] The DB password in earlier git history is rotated, or the repo history
      restarted, before handover.
- [ ] External uptime monitor configured (section 10).

---

## 13. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `certbot: command not found` | `sudo apt install -y certbot python3-certbot-nginx` |
| certbot fails domain validation | DNS not resolving to the VPS yet (check `dig`), or port 80 blocked |
| `ERROR: 'ContainerConfig'` on recreate | legacy Compose V1 bug — `docker-compose down` then `up -d`, or install Compose V2 |
| `column "extended_offline_min" does not exist` | run the idempotent `ALTER TABLE` migration in section 4 |
| Tuya `quota is exhausted` / `Err 913` | free Trial quota spent (and Trial forbids commercial use) — move to a paid IoT Core plan / events path |
| Email not reaching Hotmail/Outlook | switch SMTP to the Brevo relay |
| WhatsApp `ContentSid is Invalid` / sandbox errors | needs a production Twilio account + Meta-approved template; set `WHATSAPP_CONTENT_SID` |
| Install page shows a placeholder, not the logo | the wrong/old file is deployed, or a paste truncated the embedded image — re-`scp` the file and re-run the two verify commands |
| DB auth fails after password change | recreate (not restart) so all services pick up the new `DATABASE_URL`; `ALTER USER` if needed |

---

*For architecture, subsystems, and the module-by-module reference, see
[README.md](README.md).*