"""
Routine learning (baseline).

Design notes (grounded in the real 12-day dataset):
  - The cafeteira is the usable signal: clean spikes up to ~2900 W, else ~0.
  - The abajur (LED lamp) maxes at 6 W and never crosses an activity
    threshold, so it is treated as a low-signal device and excluded from
    activity inference by default (still stored, still monitored for
    connectivity).
  - Activity is SPARSE: a few active minutes per day. So the robust routine
    metric is not "expected at hour X" but:
        (a) per-hour activity probability  -> where activity tends to occur
        (b) typical and maximum gap between activity events -> the basis for
            "too quiet" deviation detection, which is what actually protects
            an elderly person.

Offline / no-data periods MUST be excluded from learning, so that silence
caused by a dead plug or an expired API quota is never learned as "a quiet
day". We rebuild coverage from the readings themselves and only learn from
periods where the device was genuinely reporting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import median

# Per-device activity threshold in watts. A reading at/above this counts as
# an "activity event" (human interaction). 50 W cleanly separates the
# cafeteira's ~2900 W spikes from its ~0 W standby.
ACTIVITY_THRESHOLD_W = {
    "default": 50.0,
}
# Devices whose signal is too weak to infer activity from (still monitored
# for connectivity, just not used for the routine baseline).
LOW_SIGNAL_DEVICES = {"Abajur de quarto"}

# If two consecutive readings are farther apart than this, we treat the
# span between them as a DATA GAP (device offline / collector down / quota
# exhausted) and exclude it from both coverage and gap statistics.
DATA_GAP_MINUTES = 5


@dataclass
class Reading:
    ts: datetime          # timezone-aware, local time
    device: str
    power_w: float
    online: bool


@dataclass
class RoutineBaseline:
    device: str
    threshold_w: float
    days_observed: float
    total_active_events: int
    hourly_activity_prob: dict[int, float] = field(default_factory=dict)
    typical_gap_min: float = 0.0     # median gap between activity events (awake hours)
    max_normal_gap_min: float = 0.0  # the "this long is still normal" ceiling
    quiet_hours: set[int] = field(default_factory=set)  # habitually inactive (e.g. night)

    def summary(self) -> str:
        top = sorted(self.hourly_activity_prob.items(),
                     key=lambda kv: kv[1], reverse=True)[:5]
        top_str = ", ".join(f"{h:02d}h ({p:.0%})" for h, p in top)
        return (
            f"Device: {self.device}\n"
            f"  Observed span (excl. gaps): {self.days_observed:.1f} days\n"
            f"  Activity events: {self.total_active_events}\n"
            f"  Busiest hours: {top_str}\n"
            f"  Typical gap between events: {self.typical_gap_min:.0f} min\n"
            f"  Max normal gap (deviation ceiling): {self.max_normal_gap_min:.0f} min\n"
            f"  Habitual quiet hours: "
            f"{sorted(self.quiet_hours) if self.quiet_hours else 'none'}"
        )


def _threshold_for(device: str) -> float:
    return ACTIVITY_THRESHOLD_W.get(device, ACTIVITY_THRESHOLD_W["default"])


def detect_activity_events(readings: list[Reading]) -> list[datetime]:
    """Timestamps where power crossed the device threshold, de-duplicated so a
    single continuous use (e.g. a 4-minute brew) counts as ONE event, not four.
    """
    if not readings:
        return []
    thr = _threshold_for(readings[0].device)
    events: list[datetime] = []
    in_event = False
    for r in readings:
        active = r.online and r.power_w >= thr
        if active and not in_event:
            events.append(r.ts)   # rising edge = start of a use
            in_event = True
        elif not active:
            in_event = False
    return events


def _covered_spans(readings: list[Reading]) -> list[tuple[datetime, datetime]]:
    """Contiguous spans where the device was actually reporting (gaps > DATA_GAP
    excluded). Used to measure real observation time, not wall-clock time.
    """
    spans: list[tuple[datetime, datetime]] = []
    if not readings:
        return spans
    gap = timedelta(minutes=DATA_GAP_MINUTES)
    start = prev = readings[0].ts
    for r in readings[1:]:
        if r.ts - prev > gap:
            spans.append((start, prev))
            start = r.ts
        prev = r.ts
    spans.append((start, prev))
    return spans


def learn_baseline(readings: list[Reading], device: str) -> RoutineBaseline:
    """Learn the routine baseline for one device from its historical readings.
    `readings` must be for a single device, sorted by ts ascending.
    """
    threshold = _threshold_for(device)

    if device in LOW_SIGNAL_DEVICES:
        return RoutineBaseline(device=device, threshold_w=threshold,
                               days_observed=0.0, total_active_events=0)

    spans = _covered_spans(readings)
    observed_minutes = sum((e - s).total_seconds() / 60 for s, e in spans)
    days_observed = observed_minutes / (60 * 24)

    events = detect_activity_events(readings)

    # Per-hour activity probability: of the days we observed a given hour,
    # in what fraction did activity occur in that hour?
    hour_days_seen: dict[int, set] = {h: set() for h in range(24)}
    for s, e in spans:
        t = s.replace(minute=0, second=0, microsecond=0)
        while t <= e:
            hour_days_seen[t.hour].add(t.date())
            t += timedelta(hours=1)
    hour_days_active: dict[int, set] = {h: set() for h in range(24)}
    for ev in events:
        hour_days_active[ev.hour].add(ev.date())

    hourly_prob = {}
    for h in range(24):
        seen = len(hour_days_seen[h])
        hourly_prob[h] = (len(hour_days_active[h]) / seen) if seen else 0.0

    # Gaps between consecutive activity events, but only WITHIN a covered span
    # (never across a data gap, which would be a fake huge gap).
    gaps: list[float] = []
    span_of = _assign_events_to_spans(events, spans)
    for span_events in span_of.values():
        for a, b in zip(span_events, span_events[1:]):
            gaps.append((b - a).total_seconds() / 60)

    typical_gap = median(gaps) if gaps else 0.0
    # Deviation ceiling: the 90th-percentile gap, i.e. "longer than this is
    # unusual for this household". Robust for sparse data.
    max_normal_gap = _percentile(gaps, 0.90) if gaps else 0.0

    # Habitual quiet hours: hours with essentially no activity across all days.
    quiet = {h for h, p in hourly_prob.items() if p < 0.05}

    return RoutineBaseline(
        device=device,
        threshold_w=threshold,
        days_observed=days_observed,
        total_active_events=len(events),
        hourly_activity_prob=hourly_prob,
        typical_gap_min=typical_gap,
        max_normal_gap_min=max_normal_gap,
        quiet_hours=quiet,
    )


def _assign_events_to_spans(events, spans):
    out: dict[int, list[datetime]] = {i: [] for i in range(len(spans))}
    for ev in events:
        for i, (s, e) in enumerate(spans):
            if s <= ev <= e:
                out[i].append(ev)
                break
    return out


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    idx = min(len(xs) - 1, int(round(q * (len(xs) - 1))))
    return xs[idx]