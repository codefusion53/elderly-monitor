"""
Interface: consumption (progress) chart — last N hours of power per device.

Kept as a standalone entry point for convenience; shares the same data layer
as interface.make_charts. Prefer `python -m interface.make_charts --consumption`
for the unified CLI; this module is the focused, single-purpose equivalent.

Run from project root, next to .env:
    python -m interface.make_progress_chart
    CHART_HOURS=96 python -m interface.make_progress_chart
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from interface.data_access import connect, device_names, load_readings, TZ

HOURS = int(os.getenv("CHART_HOURS", "48"))
OUTPUT = os.getenv("CHART_OUT", "progress_chart.png")


def main():
    conn = connect()
    try:
        series = {}
        for name in device_names(conn):
            rs = load_readings(conn, name)
            if not rs:
                continue
            cutoff = rs[-1].ts - timedelta(hours=HOURS)
            pts = [(r.ts, r.power_w) for r in rs if r.ts >= cutoff]
            if pts:
                series[name] = pts
    finally:
        conn.close()

    if not series:
        print("No readings in the selected window - is the collector running?")
        return

    n = len(series)
    fig, axes = plt.subplots(n, 1, figsize=(12, 3.2 * n), sharex=True)
    if n == 1:
        axes = [axes]
    for ax, (name, pts) in zip(axes, sorted(series.items())):
        ts = [p[0] for p in pts]
        w = [p[1] for p in pts]
        ax.plot(ts, w, linewidth=1.2)
        ax.fill_between(ts, w, alpha=0.15)
        ax.set_ylabel("Watts")
        ax.set_title(f"{name}  (pico: {max(w):.0f} W)", loc="left", fontsize=11)
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %H:%M"))
    axes[-1].set_xlabel(f"Hora local ({TZ})")
    fig.suptitle(f"Consumo das tomadas - últimas {HOURS}h "
                 f"(gerado {datetime.now().strftime('%d/%m %H:%M')})", fontsize=13)
    fig.tight_layout()
    fig.savefig(OUTPUT, dpi=150)
    total = sum(len(v) for v in series.values())
    print(f"Saved {OUTPUT}  ({total} readings across {n} devices)")


if __name__ == "__main__":
    main()
