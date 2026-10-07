# Elderly Monitoring System — Installation Guide

This document describes how to install, configure, run, and maintain the Elderly Monitoring System on an Ubuntu VPS.

The application consists of four Docker Compose services:

- `db` — PostgreSQL
- `collector` — reads Tuya smart-plug telemetry
- `web` — FastAPI dashboard and authentication
- `alerting` — email/WhatsApp notification engine

The system is designed around the principle that **"no data" is never confused with "no activity"**. Connectivity gaps are tracked separately from activity inference.

---

## 1. Requirements

### Server

Recommended production environment:

- Ubuntu 22.04 LTS or newer
- Docker Engine
- Docker Compose V2
- SSH access with sudo/root privileges
- A public IP address
- A domain name for production HTTPS access

### External services

The application requires:

- Tuya IoT Cloud credentials
- SMTP credentials if email alerts are enabled
- WhatsApp Business API credentials if WhatsApp alerts are enabled

Do not commit credentials to Git.

---

## 2. Get the source code

Clone the repository to the server:

```bash
sudo mkdir -p /opt/elderly-monitor
sudo chown "$USER":"$USER" /opt/elderly-monitor

cd /opt
git clone <REPOSITORY_URL> elderly-monitor
cd /opt/elderly-monitor
```

If the repository is already present, update it with:

```bash
cd /opt/elderly-monitor
git pull
```

---

## 3. Install Docker

On Ubuntu, install Docker using Docker's official installation instructions.

After installation, verify:

```bash
docker --version
docker compose version
```

Enable Docker at boot:

```bash
sudo systemctl enable docker
sudo systemctl start docker
```

Verify:

```bash
systemctl is-enabled docker
systemctl is-active docker
```

The project uses `docker compose` (Compose V2). The legacy `docker-compose` V1.29 binary is known to have container recreation problems.

---

## 4. Configure environment variables

Copy the example environment file:

```bash
cd /opt/elderly-monitor
cp .env.example .env
```

Edit it:

```bash
nano .env
```

Configure the required values:

```env
TUYA_REGION=<tuya-region>
TUYA_ACCESS_ID=<tuya-access-id>
TUYA_ACCESS_SECRET=<tuya-access-secret>

DB_PASSWORD=<strong-database-password>
DATABASE_URL=postgresql://monitor:<strong-database-password>@db:5432/monitor

POLL_INTERVAL_SECONDS=60
OFFLINE_TOLERANCE_MINUTES=20

SMTP_HOST=<smtp-host>
SMTP_PORT=<smtp-port>
SMTP_USER=<smtp-user>
SMTP_PASS=<smtp-password>
SMTP_FROM=<sender-address>

WHATSAPP_API_URL=<whatsapp-api-url>
WHATSAPP_API_TOKEN=<whatsapp-api-token>
WHATSAPP_FROM=<whatsapp-sender>
```

Use the actual keys supported by the current `.env.example`.

Important:

- Do not commit `.env`.
- Do not put real passwords, Tuya secrets, SMTP passwords, or API tokens in documentation.
- `.env` values are read literally; avoid unnecessary quotes and trailing spaces.
- Restrict the file:

```bash
chmod 600 .env
```

The README specifies that the database password is supplied through `DB_PASSWORD` and interpolated by Docker Compose.

---

## 5. Build and start the application

From the project directory:

```bash
cd /opt/elderly-monitor
docker compose up -d --build
```

Check all services:

```bash
docker compose ps
```

Expected services:

```text
db
collector
web
alerting
```

All should be `Up`.

---

## 6. Database initialization

### Fresh installation

On a fresh installation, `schema.sql` is applied automatically when the PostgreSQL volume is created.

No manual schema command is normally required.

### Existing database

If an existing database predates the alert-threshold columns, apply the idempotent migration:

```bash
docker compose exec -T db psql -U monitor -d monitor -c "ALTER TABLE residence_settings ADD COLUMN IF NOT EXISTS extended_offline_min INTEGER NOT NULL DEFAULT 180, ADD COLUMN IF NOT EXISTS total_offline_critical_min INTEGER NOT NULL DEFAULT 40;"
```

**Do not use `docker compose down -v` on a production installation.** The `-v` option removes the PostgreSQL volume and can delete the application's database data.

---

## 7. Create an administrator

Create the initial admin user from inside the web container:

```bash
docker compose exec web python -c "from api.auth import create_user; create_user('admin','PICK_A_PASSWORD',role='admin')"
```

Replace `PICK_A_PASSWORD` with a strong, unique password.

Do not put the real password in Git, README files, shell history, or support messages.

The application supports:

- `caregiver` — dashboard access
- `admin` — dashboard and administration/settings access

---

## 8. Verify the application

Check the containers:

```bash
docker compose ps
```

Check the API health endpoint from the VPS:

```bash
curl -s http://127.0.0.1:8000/api/health
```

Expected:

```json
{"ok":true}
```

Check the login page:

```bash
curl -I http://127.0.0.1:8000/login
```

The web application normally listens on port `8000`.

For a secure production deployment, keep the application bound to localhost and expose it through a reverse proxy.

Recommended Compose binding:

```yaml
ports:
  - "127.0.0.1:8000:8000"
```

---

## 9. Test the Tuya connection

The repository includes diagnostics in `check/`.

Run:

```bash
cd /opt/elderly-monitor
python3 check/tuya_connection_test.py
```

The diagnostic checks:

1. Tuya authentication
2. Device discovery
3. Live device status
4. Energy-monitoring data points

Another diagnostic is available for region/credential troubleshooting:

```bash
python3 check/tuya_region_sweep.py
```

Never paste Tuya access secrets into tickets, chat messages, or documentation.

### Important Tuya behavior

The device-list endpoint may return:

```text
online: None
```

This is not necessarily a connectivity failure. The per-device detail endpoint is the authoritative liveness source used by the application.

---

## 10. Check collector logs

The collector polls devices according to `POLL_INTERVAL_SECONDS`.

View logs:

```bash
docker compose logs -f collector
```

Or:

```bash
docker compose logs collector --tail=50
```

A healthy collector should connect to PostgreSQL and periodically report device readings.

The connectivity state machine is:

```text
unknown -> online -> offline_suspected -> offline_confirmed
             ^              |                    |
             +--------------+---- back_online ---+
```

A short connectivity interruption does not immediately create an alert. After `OFFLINE_TOLERANCE_MINUTES`, an offline device becomes `offline_confirmed`.

---

## 11. Check alerting

View alerting logs:

```bash
docker compose logs -f alerting
```

The alerting service runs a cycle every 300 seconds in the Docker Compose configuration.

The notification behavior is stateful:

- routine YELLOW and return-to-GREEN → email to `all`-tier contacts
- critical RED activity or SYSTEM/offline → WhatsApp + email to all contacts

Email works through SMTP.

WhatsApp requires the client's Business API account/configuration.

Unconfigured notification channels fail safely.

---

## 12. Accessing the dashboard through Nginx

For external access, do not expose the FastAPI/Uvicorn port directly.

Keep Docker on:

```text
127.0.0.1:8000
```

Install Nginx:

```bash
sudo apt update
sudo apt install -y nginx
```

Create a site configuration:

```bash
sudo nano /etc/nginx/sites-available/elderly-monitor
```

For an initial HTTP-only deployment by IP:

```nginx
server {
    listen 80;
    listen [::]:80;

    server_name <SERVER_IP_OR_DOMAIN>;

    location / {
        proxy_pass http://127.0.0.1:8000;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable the configuration:

```bash
sudo ln -s /etc/nginx/sites-available/elderly-monitor /etc/nginx/sites-enabled/elderly-monitor
```

Remove the default site if it is still enabled:

```bash
sudo rm -f /etc/nginx/sites-enabled/default
```

Test Nginx:

```bash
sudo nginx -t
```

Restart:

```bash
sudo systemctl restart nginx
```

The dashboard can then be accessed without specifying port `8000`:

```text
http://<SERVER_IP>/
```

### HTTPS

For real production use, the application should run behind HTTPS because it handles login credentials and sensitive routine information.

Use a domain name pointing to the VPS and configure an HTTPS certificate with Let's Encrypt/Certbot.

The desired production architecture is:

```text
https://admin.example.com
          |
          v
       Nginx :443
          |
       HTTPS/TLS
          |
          v
  127.0.0.1:8000
          |
          v
    Docker web service
```

Do not configure the browser to use `https://<SERVER_IP>:8000` unless the application itself is configured to serve TLS. Uvicorn on port 8000 is normally plain HTTP.

---

## 13. Firewall

Only expose the ports that are required.

Typical production requirements:

- SSH: `22`
- HTTP: `80`
- HTTPS: `443`

Do **not** expose PostgreSQL (`5432`) publicly.

If UFW is used:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Check:

```bash
sudo ufw status
```

Verify PostgreSQL is not publicly bound:

```bash
ss -tlnp | grep 5432
```

The application should keep PostgreSQL bound to localhost where applicable, and Docker Compose should not publish it to `0.0.0.0`.

---

## 14. Useful operational commands

### Check all services

```bash
docker compose ps
```

### Follow all logs

```bash
docker compose logs -f
```

### Collector

```bash
docker compose logs -f collector
```

### Web

```bash
docker compose logs -f web
```

### Alerting

```bash
docker compose logs -f alerting
```

### PostgreSQL

```bash
docker compose logs -f db
```

### Restart services

```bash
docker compose restart
```

### Apply environment/Compose configuration changes

Recreate the containers:

```bash
docker compose down
docker compose up -d
```

This does **not** delete the database volume.

Never use:

```bash
docker compose down -v
```

unless you intentionally want to remove the database volume.

### Rebuild after code changes

```bash
docker compose up -d --build
```

---

## 15. Health and database checks

API health:

```bash
curl -s http://127.0.0.1:8000/api/health
```

Database reading count:

```bash
docker compose exec db psql -U monitor -d monitor -c "SELECT count(*), min(ts), max(ts) FROM readings;"
```

The README expects approximately 120 rows/hour for two devices under a 60-second polling interval, with the newest timestamp within roughly two minutes under normal operation.

---

## 16. Charts and reports

From the project root, the chart CLI can be used during development/analysis.

All charts:

```bash
python -m interface.make_charts --all
```

Routine only:

```bash
python -m interface.make_charts --routine
```

Consumption for the last 48 hours:

```bash
python -m interface.make_charts --consumption --hours 48
```

Specify an output directory:

```bash
python -m interface.make_charts --routine --out reports/
```

The chart timezone follows `CHART_TZ`, defaulting to:

```text
Europe/Lisbon
```

---

## 17. Backups

The PostgreSQL database contains the collected telemetry and application data and should be backed up regularly.

Recommended production policy:

- Daily `pg_dump`
- Store backups off the VPS
- Keep multiple historical backups
- Periodically test restoring a backup

Example database dump:

```bash
docker compose exec -T db pg_dump -U monitor -d monitor | gzip > elderly-monitor-$(date +%Y-%m-%d).sql.gz
```

Do not store the only backup on the same VPS as the database.

---

## 18. Updating the application

Before updating, make a database backup.

Then:

```bash
cd /opt/elderly-monitor

git pull

docker compose up -d --build
```

Check:

```bash
docker compose ps
docker compose logs --tail=50
```

Verify:

```bash
curl -s http://127.0.0.1:8000/api/health
```

If configuration changes require complete recreation:

```bash
docker compose down
docker compose up -d --build
```

Do not use `-v`.

---

## 19. Production security checklist

Before handing the server to the client:

- [ ] Rotate any credentials that were exposed during development/deployment.
- [ ] Use a strong unique database password.
- [ ] Keep `.env` out of Git.
- [ ] Set `.env` permissions to `600`.
- [ ] Do not expose PostgreSQL publicly.
- [ ] Keep the web container on `127.0.0.1:8000`.
- [ ] Use Nginx as the public reverse proxy.
- [ ] Use HTTPS before real production use.
- [ ] Configure a firewall.
- [ ] Use a non-root SSH account for normal administration where possible.
- [ ] Disable direct root SSH login when operationally appropriate.
- [ ] Use SSH keys rather than password authentication where possible.
- [ ] Configure database backups.
- [ ] Test restoring a backup.
- [ ] Confirm Tuya credentials and region.
- [ ] Confirm all expected devices appear in the Tuya diagnostic.
- [ ] Confirm collector logs show current readings.
- [ ] Confirm alerting configuration.
- [ ] Test caregiver login.
- [ ] Test admin login.
- [ ] Test logout/session expiration.
- [ ] Test the dashboard from an external network.
- [ ] Test an alert before handover.

---

## 20. Troubleshooting

### Containers are not running

```bash
docker compose ps
docker compose logs --tail=100
```

### Web page does not load

Check:

```bash
docker compose ps
docker compose logs web --tail=100
curl -I http://127.0.0.1:8000/login
```

If using Nginx:

```bash
sudo nginx -t
sudo systemctl status nginx
```

### Database connection fails

Check:

```bash
docker compose logs db --tail=100
docker compose logs collector --tail=100
```

Confirm the database configuration in `.env`.

The collector is designed to retry the database connection during startup, but an incorrect database password will ultimately fail.

### Tuya authentication/device problems

Run:

```bash
python3 check/tuya_connection_test.py
```

Check:

- `TUYA_REGION`
- `TUYA_ACCESS_ID`
- `TUYA_ACCESS_SECRET`
- Tuya IoT project permissions
- Tuya API availability/quota

Tuya's free Trial Edition of IoT Core has limited quota/period. If the quota is exhausted, polling can fail until the subscription is extended.

### Login does not work

Confirm that an admin user was created:

```bash
docker compose exec web python -c "from api.auth import create_user; create_user('admin','PICK_A_PASSWORD',role='admin')"
```

Use a new strong password rather than reusing an existing credential.

### HTTPS gives `ERR_SSL_PROTOCOL_ERROR`

If Nginx is only configured for HTTP, use:

```text
http://<SERVER_IP>
```

Do not use:

```text
https://<SERVER_IP>:8000
```

until TLS has actually been configured.

---

## 21. Reboot test

Because all services use `restart: unless-stopped`, they should return automatically after a server reboot when Docker is enabled at boot.

Test:

```bash
sudo reboot
```

After reconnecting:

```bash
cd /opt/elderly-monitor
docker compose ps
```

All four services should be running.

---

## 22. Final handover checklist

Before declaring the installation complete:

```text
[ ] Docker starts automatically
[ ] PostgreSQL starts automatically
[ ] Database schema is present
[ ] Collector is receiving Tuya data
[ ] Devices are visible
[ ] Connectivity monitoring works
[ ] Web dashboard loads
[ ] Caregiver login works
[ ] Admin login works
[ ] Settings page works
[ ] Alerting service runs
[ ] Email alerts tested
[ ] WhatsApp alerts tested if configured
[ ] Nginx reverse proxy works
[ ] HTTPS certificate installed
[ ] Firewall configured
[ ] PostgreSQL is not publicly exposed
[ ] Database backup created
[ ] Backup restore tested
[ ] Deployment credentials rotated
[ ] Client access tested
```

---

## 23. Important data and credential notes

The repository contains sensitive operational configuration. Never commit:

- `.env`
- Tuya access secrets
- database passwords
- SMTP passwords
- WhatsApp API tokens
- server passwords
- private SSH keys

The database password should exist only in the environment configuration.

If a credential has ever been committed to Git or shared outside the intended secure channel, rotate it before production handover.

