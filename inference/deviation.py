"""
Deviation detection and semáforo (traffic-light) state.

Given a learned RoutineBaseline and the current situation, decide the state:

    GREEN  - within normal patterns; activity is recent enough
    YELLOW - no recent activity and the quiet stretch is getting unusual,
             OR we're mid-way to the deviation ceiling during waking hours
    RED    - the quiet stretch has exceeded the household's normal ceiling
             during hours the person is usually active, OR the system itself
             is offline (no data) -> a SYSTEM alert, never confused with the
             person being inactive.

Key protective principle:
    "no data" (device/collector offline) is reported as its OWN red state
    (system health), explicitly distinct from "person inactive". The family
    is told which one it is.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .baseline import RoutineBaseline

# Fraction of the max-normal-gap at which we escalate GREEN -> YELLOW.
YELLOW_FRACTION = 0.75


@dataclass
class StateResult:
    state: str            # "GREEN" | "YELLOW" | "RED"
    reason: str           # human-readable, ready for the family
    category: str         # "activity" | "system"
    minutes_since_activity: float | None
    ceiling_min: float


def _in_waking_hours(hour: int, baseline: RoutineBaseline) -> bool:
    """Waking = not a habitual quiet hour. Deviation only alarms during hours
    the person is normally capable of activity, so a normal night's sleep
    never trips a red."""
    return hour not in baseline.quiet_hours


def evaluate_state(
    baseline: RoutineBaseline,
    last_activity_ts: datetime | None,
    now: datetime,
    system_online: bool,
) -> StateResult:
    """Decide the current semáforo state for one residence/device."""

    ceiling = baseline.max_normal_gap_min or 0.0

    # 1) System health takes precedence: no data is a SYSTEM problem.
    if not system_online:
        return StateResult(
            state="RED",
            reason="Sistema sem ligação à tomada: não é possível monitorizar "
                   "(falha técnica, não sinal sobre a pessoa).",
            category="system",
            minutes_since_activity=None,
            ceiling_min=ceiling,
        )

    # 2) Low-signal / unlearned baseline: we can't infer activity reliably.
    if baseline.total_active_events == 0 or ceiling == 0.0:
        return StateResult(
            state="GREEN",
            reason="A recolher dados; padrão de rotina ainda a ser aprendido.",
            category="activity",
            minutes_since_activity=None,
            ceiling_min=ceiling,
        )

    if last_activity_ts is None:
        mins = None
    else:
        mins = (now - last_activity_ts).total_seconds() / 60

    # 3) Never alarm during habitual quiet hours (e.g. night). Hold GREEN.
    if not _in_waking_hours(now.hour, baseline):
        return StateResult(
            state="GREEN",
            reason="Período habitualmente sem atividade (ex.: noite).",
            category="activity",
            minutes_since_activity=mins,
            ceiling_min=ceiling,
        )

    if mins is None:
        return StateResult(
            state="YELLOW",
            reason="Ainda sem atividade registada.",
            category="activity",
            minutes_since_activity=None,
            ceiling_min=ceiling,
        )

    # 4) Compare the current quiet stretch against the learned ceiling.
    if mins >= ceiling:
        return StateResult(
            state="RED",
            reason=f"Sem atividade há {mins:.0f} min, acima do normal para "
                   f"esta casa ({ceiling:.0f} min). Desvio significativo.",
            category="activity",
            minutes_since_activity=mins,
            ceiling_min=ceiling,
        )
    if mins >= YELLOW_FRACTION * ceiling:
        return StateResult(
            state="YELLOW",
            reason=f"Sem atividade há {mins:.0f} min, a aproximar-se do "
                   f"limite habitual ({ceiling:.0f} min).",
            category="activity",
            minutes_since_activity=mins,
            ceiling_min=ceiling,
        )

    return StateResult(
        state="GREEN",
        reason=f"Atividade recente (há {mins:.0f} min). Tudo normal.",
        category="activity",
        minutes_since_activity=mins,
        ceiling_min=ceiling,
    )