"""
Interface: learned-routine chart + day-by-day state strip (Milestone 2 evidence).

Standalone entry point sharing the same data layer as interface.make_charts.
Prefer `python -m interface.make_charts --routine` for the unified CLI; this
module is the focused, single-purpose equivalent.

Run from project root, next to .env:
    python -m interface.make_routine_chart
    ROUTINE_DEVICE="Cafeteira cozinha" python -m interface.make_routine_chart
"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from inference.baseline import learn_baseline
from inference.report import validate_days
from interface.data_access import connect, device_names, load_readings, TZ

OUTPUT = os.getenv("CHART_OUT", "routine_marco2.png")
ONLY_DEVICE = os.getenv("ROUTINE_DEVICE")  # optional: restrict to one device

STATE_COLORS = {
    "GREEN": "#2e9e5b", "YELLOW": "#e6b800",
    "RED": "#d64545", "SEM DADOS": "#b0b7c0",
}


def render(base, days, device, output):
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
    fig.savefig(output, dpi=160, bbox_inches="tight")
    plt.close(fig)


def main():
    conn = connect()
    try:
        names = device_names(conn)
        if ONLY_DEVICE:
            names = [n for n in names if n == ONLY_DEVICE]
        made = False
        for device in names:
            readings = load_readings(conn, device)
            if not readings:
                continue
            base = learn_baseline(readings, device)
            if base.total_active_events == 0:
                print(f"{device}: low/no activity signal, skipped.")
                continue
            days = validate_days(readings, base)
            # if multiple devices produce charts, suffix the filename
            out = OUTPUT if not made else OUTPUT.replace(".png", f"_{device.split()[0].lower()}.png")
            render(base, days, device, out)
            print(f"Saved {out}  (peaks: "
                  f"{sorted(top_hours(base))}, {base.total_active_events} events)")
            made = True
        if not made:
            print("No device produced a routine chart.")
    finally:
        conn.close()


def top_hours(base):
    return [h for h, _ in sorted(base.hourly_activity_prob.items(),
            key=lambda kv: kv[1], reverse=True)[:2]]


if __name__ == "__main__":
    main()
