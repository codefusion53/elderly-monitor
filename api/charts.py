"""
Phase 3 - On-request chart rendering for the admin page.

Renders the routine and consumption charts to PNG bytes (in memory, no files),
with a short cache so rapid page refreshes don't re-render every time.
Reuses the inference/baseline logic; kept independent of interface.make_charts
so the web layer has no file-writing side effects.
"""
from __future__ import annotations

import io
import time
from datetime import timedelta

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from inference.baseline import learn_baseline
from inference.report import validate_days
from interface.data_access import connect, device_names, load_readings, TZ

STATE_COLORS = {"GREEN": "#2e9e5b", "YELLOW": "#e6b800",
                "RED": "#d64545", "SEM DADOS": "#b0b7c0"}

# simple in-memory cache: {key: (timestamp, png_bytes)}
_CACHE: dict[str, tuple[float, bytes]] = {}
_CACHE_TTL = 60  # seconds


def _cached(key: str, producer):
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    png = producer()
    _CACHE[key] = (now, png)
    return png


def _fig_to_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def routine_png() -> bytes | None:
    def produce():
        conn = connect()
        try:
            # pick the first device that yields a usable routine
            for name in device_names(conn):
                readings = load_readings(conn, name)
                if not readings:
                    continue
                base = learn_baseline(readings, name)
                if base.total_active_events == 0:
                    continue
                days = validate_days(readings, base)
                return _render_routine(base, days, name)
            return _placeholder("Sem dados de rotina suficientes ainda.")
        finally:
            conn.close()
    return _cached("routine", produce)


def consumption_png(hours: int = 48) -> bytes | None:
    def produce():
        conn = connect()
        try:
            series = {}
            for name in device_names(conn):
                rs = load_readings(conn, name)
                if not rs:
                    continue
                cutoff = rs[-1].ts - timedelta(hours=hours)
                pts = [(r.ts, r.power_w) for r in rs if r.ts >= cutoff]
                if pts:
                    series[name] = pts
            if not series:
                return _placeholder("Sem leituras recentes.")
            return _render_consumption(series, hours)
        finally:
            conn.close()
    return _cached(f"consumption_{hours}", produce)


def _render_routine(base, days, device) -> bytes:
    fig = plt.figure(figsize=(11, 6.6))
    gs = fig.add_gridspec(2, 1, height_ratios=[3, 1.15], hspace=0.42)
    ax = fig.add_subplot(gs[0])
    hours = list(range(24))
    probs = [base.hourly_activity_prob.get(h, 0) * 100 for h in hours]
    bars = ax.bar(hours, probs, width=0.82, color="#c9d6e5", edgecolor="#9db3cc")
    top = {h for h, _ in sorted(base.hourly_activity_prob.items(),
           key=lambda kv: kv[1], reverse=True)[:2]}
    for h in top:
        bars[h].set_color("#2e6da4"); bars[h].set_edgecolor("#1f4e79")
    for h in base.quiet_hours:
        ax.axvspan(h - 0.5, h + 0.5, color="#f0f0f2", zorder=0)
    for h in top:
        ax.annotate(f"{probs[h]:.0f}%", (h, probs[h]), ha="center", va="bottom",
                    fontsize=9, fontweight="bold", color="#1f4e79")
    ax.set_xticks(hours); ax.set_xticklabels([f"{h:02d}" for h in hours], fontsize=8)
    ax.set_xlabel("Hora do dia (local)", fontsize=9)
    ax.set_ylabel("Probabilidade de atividade", fontsize=9)
    ax.set_ylim(0, max(probs + [10]) * 1.25)
    ax.set_title(f"Rotina aprendida - {device}  ({base.total_active_events} eventos, "
                 f"{base.days_observed:.0f} dias)", fontsize=11, loc="left", pad=10)
    ax.grid(axis="y", alpha=0.25); ax.set_axisbelow(True)
    ax.legend(handles=[Patch(color="#2e6da4", label="Pico"),
                       Patch(color="#c9d6e5", label="Ativo"),
                       Patch(color="#f0f0f2", label="Calmo")],
              loc="upper right", fontsize=8, framealpha=0.9)
    ax2 = fig.add_subplot(gs[1])
    labels, states = [], []
    for day, n, worst, flag in days:
        labels.append(day.strftime("%d/%m")); states.append(flag)
    for i, st in enumerate(states):
        ax2.add_patch(plt.Rectangle((i, 0), 0.92, 1, color=STATE_COLORS[st]))
        ax2.text(i + 0.46, 0.5, st.replace("SEM DADOS", "s/ dados"),
                 ha="center", va="center", fontsize=6.4,
                 color="white" if st != "YELLOW" else "#5a4a00", fontweight="bold")
    ax2.set_xlim(0, len(states)); ax2.set_ylim(0, 1)
    ax2.set_xticks([i + 0.46 for i in range(len(labels))])
    ax2.set_xticklabels(labels, fontsize=7); ax2.set_yticks([])
    ax2.set_title("Validacao dia a dia", fontsize=9.5, loc="left", pad=6)
    for s in ["top", "right", "left"]:
        ax2.spines[s].set_visible(False)
    return _fig_to_png(fig)


def _render_consumption(series, hours) -> bytes:
    n = len(series)
    fig, axes = plt.subplots(n, 1, figsize=(11, 2.8 * n), sharex=True)
    if n == 1:
        axes = [axes]
    for ax, (name, pts) in zip(axes, sorted(series.items())):
        ts = [p[0] for p in pts]; w = [p[1] for p in pts]
        ax.plot(ts, w, linewidth=1.1)
        ax.fill_between(ts, w, alpha=0.15)
        ax.set_ylabel("W")
        ax.set_title(f"{name}  (pico: {max(w):.0f} W)", loc="left", fontsize=10)
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %H:%M"))
    axes[-1].set_xlabel(f"Hora local ({TZ})")
    fig.suptitle(f"Consumo - ultimas {hours}h", fontsize=12)
    fig.tight_layout()
    return _fig_to_png(fig)


def _placeholder(msg) -> bytes:
    fig, ax = plt.subplots(figsize=(9, 2.2))
    ax.text(0.5, 0.5, msg, ha="center", va="center", fontsize=12, color="#6b7280")
    ax.axis("off")
    return _fig_to_png(fig)
