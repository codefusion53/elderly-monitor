"""
Interface: family-facing chart generator.

One entry point for the visual deliverables:
  --routine     learned routine + day-by-day state strip (Milestone 2 evidence)
  --consumption last-N-hours power curve per device (Milestone 1 style)
  --all         both

Reads the live database (read-only). Saves PNGs into the current directory
(or --out DIR). Times shown in CHART_TZ (default Europe/Lisbon).

Run from project root, next to .env:
    python -m interface.make_charts --all
    python -m interface.make_charts --routine --out reports/
"""
from __future__ import annotations

import argparse
import os
from collections import defaultdict
from datetime import timedelta

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from inference.baseline import learn_baseline, detect_activity_events
from inference.report import validate_days
from interface.data_access import connect, device_names, load_readings, TZ

STATE_COLORS = {
    "GREEN": "#2e9e5b", "YELLOW": "#e6b800",
    "RED": "#d64545", "SEM DADOS": "#b0b7c0",
}


def routine_chart(conn, device: str, out_dir: str) -> str | None:
    readings = load_readings(conn, device)
    if not readings:
        print(f"  [routine] no readings for {device}")
        return None
    base = learn_baseline(readings, device)
    if base.total_active_events == 0:
        print(f"  [routine] {device}: low/no signal, skipped")
        return None
    days = validate_days(readings, base)

    fig = plt.figure(figsize=(12, 7.2))
    gs = fig.add_gridspec(2, 1, height_ratios=[3, 1.15], hspace=0.42)

    ax = fig.add_subplot(gs[0])
    hours = list(range(24))
    probs = [base.hourly_activity_prob.get(h, 0) * 100 for h in hours]
    bars = ax.bar(hours, probs, width=0.82, color="#c9d6e5", edgecolor="#9db3cc")
    top = sorted(base.hourly_activity_prob.items(), key=lambda kv: kv[1],
                 reverse=True)[:2]
    top_hours = {h for h, _ in top}
    for h in top_hours:
        bars[h].set_color("#2e6da4"); bars[h].set_edgecolor("#1f4e79")
    for h in base.quiet_hours:
        ax.axvspan(h - 0.5, h + 0.5, color="#f0f0f2", zorder=0)
    for h in top_hours:
        ax.annotate(f"{probs[h]:.0f}%", (h, probs[h]), ha="center", va="bottom",
                    fontsize=9, fontweight="bold", color="#1f4e79")
    ax.set_xticks(hours)
    ax.set_xticklabels([f"{h:02d}" for h in hours], fontsize=8)
    ax.set_xlabel("Hora do dia (local)", fontsize=9)
    ax.set_ylabel("Probabilidade de atividade", fontsize=9)
    ax.set_ylim(0, max(probs + [10]) * 1.25)
    ax.set_title(f"Rotina aprendida pelo sistema — {device}\n"
                 f"{base.total_active_events} eventos ao longo de "
                 f"{base.days_observed:.0f} dias observados",
                 fontsize=12, loc="left", pad=10)
    ax.grid(axis="y", alpha=0.25); ax.set_axisbelow(True)
    ax.legend(handles=[Patch(color="#2e6da4", label="Horas de pico"),
                       Patch(color="#c9d6e5", label="Outras horas ativas"),
                       Patch(color="#f0f0f2", label="Horas habitualmente calmas")],
              loc="upper right", fontsize=8, framealpha=0.9)

    ax2 = fig.add_subplot(gs[1])
    labels, states = [], []
    for day, n, worst, flag in days:
        labels.append(day.strftime("%d/%m")); states.append(flag)
    for i, st in enumerate(states):
        ax2.add_patch(plt.Rectangle((i, 0), 0.92, 1, color=STATE_COLORS[st]))
        ax2.text(i + 0.46, 0.5, st.replace("SEM DADOS", "s/ dados"),
                 ha="center", va="center", fontsize=6.6,
                 color="white" if st != "YELLOW" else "#5a4a00",
                 fontweight="bold")
    ax2.set_xlim(0, len(states)); ax2.set_ylim(0, 1)
    ax2.set_xticks([i + 0.46 for i in range(len(labels))])
    ax2.set_xticklabels(labels, fontsize=7.5); ax2.set_yticks([])
    ax2.set_title("Validação dia a dia: estado que o sistema teria atribuído a cada dia",
                  fontsize=10, loc="left", pad=6)
    for s in ["top", "right", "left"]:
        ax2.spines[s].set_visible(False)
    fig.text(0.99, 0.01,
             f"Ceiling de silêncio normal: {base.max_normal_gap_min:.0f} min  ·  "
             f"gap típico entre eventos: {base.typical_gap_min:.0f} min  ·  "
             f"hora local {TZ}", ha="right", fontsize=7.5, color="#666")

    path = os.path.join(out_dir, "routine.png")
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"  [routine] saved {path}")
    return path


def consumption_chart(conn, hours: int, out_dir: str) -> str | None:
    names = device_names(conn)
    series = {}
    for name in names:
        rs = load_readings(conn, name)
        cutoff = None
        if rs:
            cutoff = rs[-1].ts - timedelta(hours=hours)
        pts = [(r.ts, r.power_w) for r in rs if cutoff and r.ts >= cutoff]
        if pts:
            series[name] = pts
    if not series:
        print("  [consumption] no recent readings")
        return None

    n = len(series)
    fig, axes = plt.subplots(n, 1, figsize=(12, 3.2 * n), sharex=True)
    if n == 1:
        axes = [axes]
    for ax, (name, pts) in zip(axes, sorted(series.items())):
        ts = [p[0] for p in pts]; w = [p[1] for p in pts]
        ax.plot(ts, w, linewidth=1.2)
        ax.fill_between(ts, w, alpha=0.15)
        ax.set_ylabel("Watts")
        ax.set_title(f"{name}  (pico: {max(w):.0f} W)", loc="left", fontsize=11)
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %H:%M"))
    axes[-1].set_xlabel(f"Hora local ({TZ})")
    fig.suptitle(f"Consumo das tomadas — últimas {hours}h", fontsize=13)
    fig.tight_layout()
    path = os.path.join(out_dir, "consumption.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [consumption] saved {path}")
    return path


def main():
    ap = argparse.ArgumentParser(description="Family-facing chart generator")
    ap.add_argument("--routine", action="store_true", help="learned routine + state strip")
    ap.add_argument("--consumption", action="store_true", help="recent power curve")
    ap.add_argument("--all", action="store_true", help="all charts")
    ap.add_argument("--hours", type=int, default=48, help="consumption window (h)")
    ap.add_argument("--out", default=".", help="output directory")
    args = ap.parse_args()

    if not (args.routine or args.consumption or args.all):
        args.all = True
    os.makedirs(args.out, exist_ok=True)

    conn = connect()
    try:
        if args.routine or args.all:
            for name in device_names(conn):
                routine_chart(conn, name, args.out)
        if args.consumption or args.all:
            consumption_chart(conn, args.hours, args.out)
    finally:
        conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
