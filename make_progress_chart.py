"""
Progress chart - last 24h of power readings for both plugs.

Pulls from the collector's database and renders a single PNG with one
panel per device: time on the X axis, watts on the Y axis. Coffee brews
show up as tall spikes; the lamp as low plateaus.

Setup (one time):
  pip install matplotlib psycopg2-binary python-dotenv

Run (from the project root, next to .env):
  python make_progress_chart.py
Output:
  progress_chart.png
"""

import os
from datetime import datetime

import matplotlib

matplotlib.use("Agg")  # no display needed (works on a headless VPS)
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://monitor:monitor@localhost:5432/monitor"
)
HOURS = int(os.getenv("CHART_HOURS", "24"))
TIMEZONE = os.getenv("CHART_TZ", "Europe/Lisbon")
OUTPUT = "progress_chart.png"


def fetch_series(conn):
    """Return {device_name: (timestamps, watts)} for the last HOURS hours."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT d.name,
                   r.ts AT TIME ZONE %s AS local_ts,
                   COALESCE(r.cur_power_w, 0)
            FROM readings r
            JOIN devices d ON d.id = r.device_id
            WHERE r.ts > now() - make_interval(hours => %s)
            ORDER BY d.name, r.ts
            """,
            (TIMEZONE, HOURS),
        )
        series = {}
        for name, ts, watts in cur.fetchall():
            series.setdefault(name, ([], []))
            series[name][0].append(ts)
            series[name][1].append(float(watts))
        return series


def main():
    conn = psycopg2.connect(DATABASE_URL)
    series = fetch_series(conn)
    conn.close()

    if not series:
        print("No readings in the selected window - is the collector running?")
        return

    n = len(series)
    fig, axes = plt.subplots(n, 1, figsize=(12, 3.2 * n), sharex=True)
    if n == 1:
        axes = [axes]

    for ax, (name, (ts, watts)) in zip(axes, sorted(series.items())):
        ax.plot(ts, watts, linewidth=1.2)
        ax.fill_between(ts, watts, alpha=0.15)
        ax.set_ylabel("Watts")
        peak = max(watts) if watts else 0
        ax.set_title(f"{name}  (pico: {peak:.0f} W)", loc="left", fontsize=11)
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))

    axes[-1].set_xlabel(f"Hora local ({TIMEZONE})")
    fig.suptitle(
        f"Consumo das tomadas - últimas {HOURS}h  "
        f"(gerado {datetime.now().strftime('%d/%m %H:%M')})",
        fontsize=13,
    )
    fig.tight_layout()
    fig.savefig(OUTPUT, dpi=150)
    total_points = sum(len(v[0]) for v in series.values())
    print(f"Saved {OUTPUT}  ({total_points} readings across {n} devices)")


if __name__ == "__main__":
    main()