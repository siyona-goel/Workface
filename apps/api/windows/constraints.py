"""
WORKFACE — constraint evaluators: the band and the offset.  T3, TASK 5.

Day-3 committed scope is TWO of the seven shapes — `band` and `offset` — plus the
interval algebra (extraction, intersection) and the leave-one-out
`binding_constraint`. The other five evaluators are typed stubs raising
NotImplementedError with a `# Day 4` marker; they need a full day and are not
half-built here.

Pure functions over a hand-built `list[SeriesPoint]` + `list[datetime]`. No I/O,
no LLM. The physics is unit-tested Python; the model only writes the rationale.

# ---------------------------------------------------------------------------
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task
#   fg_activity_id  = a FortyGuard async job handle
# ---------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from packages.schemas.trade_window import BandSpec, ConstraintSpec, OffsetSpec
from packages.schemas.window_eval import HourState, SeriesPoint

from .psychro import dew_point_c

__all__ = [
    "HourVerdict", "Interval", "ConstraintEvaluation", "BindingConstraint",
    "evaluate_band", "evaluate_offset",
    "to_intervals", "intersect", "binding_constraint",
    "evaluate_continuity", "evaluate_cure_clock", "evaluate_composite_rate",
    "evaluate_decay_clock", "evaluate_human",
]


# --------------------------------------------------------------------------- #
# Result types (internal to the evaluator; the WindowEval assembly maps them).
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class HourVerdict:
    ts: datetime
    state: HourState
    margin: float | None = None
    reason: str | None = None


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime
    includes_marginal: bool = False

    @property
    def duration_h(self) -> float:
        return (self.end - self.start).total_seconds() / 3600.0


@dataclass
class ConstraintEvaluation:
    constraint_id: str
    per_hour: list[HourVerdict]
    intervals: list[Interval] = field(default_factory=list)
    worst_margin: float | None = None
    satisfied_hours: int = 0
    closed_hours: int = 0


@dataclass(frozen=True)
class BindingConstraint:
    """Leave-one-out result: *what is stopping me*."""
    constraint_id: str
    hours_lost: float
    would_extend_window_by_h: float


# --------------------------------------------------------------------------- #
# Governing-temperature resolution
# --------------------------------------------------------------------------- #

_GOV_PREFERENCE: dict[str, tuple[str, ...]] = {
    "air": ("t_air_c",),
    "surface": ("t_surf_c",),
    "concrete": ("t_surf_c", "t_base_material_c", "t_air_c"),
    "base_material": ("t_base_material_c", "t_surf_c"),
}


def _governing(sp: SeriesPoint, on: str | None) -> float | None:
    for field_name in _GOV_PREFERENCE.get(on or "air", ("t_air_c",)):
        v = getattr(sp, field_name)
        if v is not None:
            return v
    return None


def _step(ts: list[datetime]) -> timedelta:
    if len(ts) >= 2:
        return ts[1] - ts[0]
    return timedelta(hours=1)


def _finish(ev: ConstraintEvaluation) -> ConstraintEvaluation:
    ev.satisfied_hours = sum(1 for h in ev.per_hour if h.state in (HourState.OPEN, HourState.MARGINAL))
    ev.closed_hours = sum(1 for h in ev.per_hour if h.state is HourState.CLOSED)
    margins = [h.margin for h in ev.per_hour if h.margin is not None]
    ev.worst_margin = round(min(margins), 4) if margins else None
    ev.intervals = to_intervals(ev.per_hour, include_marginal=False)
    return ev


def _state_from_margin(margin: float, marginal_delta: float | None) -> HourState:
    md = marginal_delta or 0.0
    if margin < 0:
        return HourState.CLOSED
    if margin < md:
        return HourState.MARGINAL
    return HourState.OPEN


# --------------------------------------------------------------------------- #
# 5.1 Band
# --------------------------------------------------------------------------- #

def evaluate_band(series: list[SeriesPoint], spec: BandSpec, ts: list[datetime]) -> ConstraintEvaluation:
    """Band: t_min <= T_gov <= t_max (either bound may be absent).

        margin = the distance to whichever bound exists (min of both if both do)
        state  = closed  if margin < 0
                 marginal if 0 <= margin < marginal_delta_c
                 open     otherwise

    Handles: one-sided bounds; rh_max_pct bands; rising_required (needs t-1, so
    t_0 is no_data); hard_floor_c; and trigger_only / mitigation_not_stop rows,
    which turn a would-be-closed hour into a MITIGATION requirement (marginal) —
    cold weather does not stop a masonry crew, it obliges cold-weather procedures.
    """
    per_hour: list[HourVerdict] = []
    trigger = bool(spec.trigger_only or spec.mitigation_not_stop)

    # Advisory, non-temperature rows (e.g. air changes/hour): informational only.
    if spec.advisory_only or spec.air_changes_per_hour_min is not None:
        for t in ts:
            per_hour.append(HourVerdict(t, HourState.OPEN, None, f"{spec.label} (advisory)"))
        return _finish(ConstraintEvaluation(spec.constraint_id, per_hour))

    prev_gov: float | None = None
    for i, (sp, t) in enumerate(zip(series, ts)):
        # RH band ------------------------------------------------------------
        if spec.rh_max_pct is not None:
            rh = sp.rh_pct
            if rh is None:
                per_hour.append(HourVerdict(t, HourState.NO_DATA, None, "no RH"))
                continue
            margin = spec.rh_max_pct - rh
            state = _state_from_margin(margin, spec.marginal_delta_pct)
            per_hour.append(HourVerdict(t, state, round(margin, 3),
                                        f"RH {rh:.0f}% vs {spec.rh_max_pct:.0f}% max"))
            continue

        # Temperature band ---------------------------------------------------
        gov = _governing(sp, spec.on)
        if gov is None:
            per_hour.append(HourVerdict(t, HourState.NO_DATA, None, f"no {spec.on} temperature"))
            prev_gov = None
            continue

        if spec.t_min_c is not None and spec.t_max_c is not None:
            margin = min(gov - spec.t_min_c, spec.t_max_c - gov)
        elif spec.t_min_c is not None:
            margin = gov - spec.t_min_c
        elif spec.t_max_c is not None:
            margin = spec.t_max_c - gov
        else:
            # No temperature bound at all (e.g. a pure trigger with only a note).
            per_hour.append(HourVerdict(t, HourState.OPEN, None, spec.label))
            prev_gov = gov
            continue

        if spec.hard_floor_c is not None:
            margin = min(margin, gov - spec.hard_floor_c)

        state = _state_from_margin(margin, spec.marginal_delta_c)
        reason = f"{spec.on} {gov:.1f} C, margin {margin:+.1f} C"

        # rising_required: t_0 can never confirm "and rising" -> no_data.
        if spec.rising_required:
            if prev_gov is None:
                per_hour.append(HourVerdict(t, HourState.NO_DATA, round(margin, 3),
                                            "first sample — 'and rising' unconfirmable"))
                prev_gov = gov
                continue
            if gov <= prev_gov:
                state = HourState.CLOSED
                reason += "; not rising"

        # trigger_only / mitigation_not_stop: a closed hour becomes mitigation.
        if trigger and state is HourState.CLOSED:
            state = HourState.MARGINAL
            reason += "; mitigation required (trigger, not a stop)"

        per_hour.append(HourVerdict(t, state, round(margin, 3), reason))
        prev_gov = gov

    return _finish(ConstraintEvaluation(spec.constraint_id, per_hour))


# --------------------------------------------------------------------------- #
# 5.2 Offset — the one that wins the demo
# --------------------------------------------------------------------------- #

def evaluate_offset(series: list[SeriesPoint], spec: OffsetSpec, ts: list[datetime]) -> ConstraintEvaluation:
    """Offset: T_surface >= T_dew + delta   (delta = 2.8 C for SSPC-PA 1).

        margin = T_surface - T_dew - delta

    T_dew comes from the series when present, else psychro.dew_point_c(air, rh).
    If EITHER t_surf_c or (t_air_c and rh_pct) is missing -> NO_DATA. Fail closed:
    never guess a dew point. delta_c = 0.0 (sealant) means "at or above dew point".
    requires_dry adds a wet-surface veto (here: a margin below zero reads as wet).
    """
    per_hour: list[HourVerdict] = []
    delta = spec.delta_c

    for sp, t in zip(series, ts):
        surf = sp.t_surf_c
        dew = sp.t_dew_c
        if dew is None and sp.t_air_c is not None and sp.rh_pct is not None:
            dew = dew_point_c(sp.t_air_c, sp.rh_pct)
        if surf is None or dew is None:
            per_hour.append(HourVerdict(t, HourState.NO_DATA, None,
                                        "missing surface or dew point — fail closed, never guess"))
            continue

        margin = surf - dew - delta
        state = _state_from_margin(margin, spec.marginal_delta_c)
        need = "at/above dew point" if delta == 0.0 else f"dew point + {delta:.1f} C"
        reason = f"surface {surf:.1f} C, {surf - dew:.1f} C above dew point; need {need} (margin {margin:+.1f} C)"
        if spec.requires_dry and margin < 0:
            reason += "; surface at/below dew point — wet, must be dry"
        per_hour.append(HourVerdict(t, state, round(margin, 3), reason))

    return _finish(ConstraintEvaluation(spec.constraint_id, per_hour))


# --------------------------------------------------------------------------- #
# 5.3 Interval extraction, intersection, binding constraint
# --------------------------------------------------------------------------- #

def to_intervals(per_hour: list[HourVerdict], include_marginal: bool = False) -> list[Interval]:
    """Contiguous runs of open (or open+marginal) hours, as [start, end) intervals.

    Each cell spans one step; an interval's end is the last cell's ts plus the step.
    """
    if not per_hour:
        return []
    usable = {HourState.OPEN, HourState.MARGINAL} if include_marginal else {HourState.OPEN}
    ts = [h.ts for h in per_hour]
    step = _step(ts)
    out: list[Interval] = []
    run_start: datetime | None = None
    last: datetime | None = None
    for h in per_hour:
        if h.state in usable:
            if run_start is None:
                run_start = h.ts
            last = h.ts
        else:
            if run_start is not None and last is not None:
                out.append(Interval(run_start, last + step, include_marginal))
            run_start = last = None
    if run_start is not None and last is not None:
        out.append(Interval(run_start, last + step, include_marginal))
    return out


def closed_intervals(per_hour: list[HourVerdict]) -> list[Interval]:
    """Contiguous runs of CLOSED hours — the complement view, for 'one closure' asserts."""
    if not per_hour:
        return []
    step = _step([h.ts for h in per_hour])
    out: list[Interval] = []
    run_start: datetime | None = None
    last: datetime | None = None
    for h in per_hour:
        if h.state is HourState.CLOSED:
            if run_start is None:
                run_start = h.ts
            last = h.ts
        else:
            if run_start is not None and last is not None:
                out.append(Interval(run_start, last + step))
            run_start = last = None
    if run_start is not None and last is not None:
        out.append(Interval(run_start, last + step))
    return out


def intersect(a: list[Interval], b: list[Interval]) -> list[Interval]:
    """Interval-list intersection (both assumed sorted, non-overlapping)."""
    out: list[Interval] = []
    i = j = 0
    while i < len(a) and j < len(b):
        start = max(a[i].start, b[j].start)
        end = min(a[i].end, b[j].end)
        if start < end:
            out.append(Interval(start, end, a[i].includes_marginal or b[j].includes_marginal))
        if a[i].end < b[j].end:
            i += 1
        else:
            j += 1
    return out


def _longest_h(intervals: list[Interval]) -> float:
    return max((iv.duration_h for iv in intervals), default=0.0)


def binding_constraint(results: dict[str, ConstraintEvaluation],
                       include_marginal: bool = True) -> BindingConstraint | None:
    """The constraint whose REMOVAL would most extend the longest open interval.

    Computed by leave-one-out: for each constraint, re-intersect the others and
    measure how much the longest usable interval grows. That is a different (and
    better) question than 'which closes the most hours' — a constraint can close
    many scattered hours yet not be what is stopping you, while another closes one
    hour in the middle of the best window and is decisive.
    """
    if not results:
        return None

    # Full horizon span, used as the identity element when leaving out the only
    # other constraint(s), so an empty "others" set means unconstrained.
    any_ph = next(iter(results.values())).per_hour
    ts = [h.ts for h in any_ph]
    horizon = [Interval(ts[0], ts[-1] + _step(ts), include_marginal)] if ts else []

    per_constraint = {cid: to_intervals(ev.per_hour, include_marginal) for cid, ev in results.items()}

    def intersect_all(cids: list[str]) -> list[Interval]:
        acc = horizon
        for cid in cids:
            acc = intersect(acc, per_constraint[cid])
        return acc

    all_ids = list(results)
    baseline = _longest_h(intersect_all(all_ids))

    best: BindingConstraint | None = None
    for cid in all_ids:
        others = [c for c in all_ids if c != cid]
        gain = _longest_h(intersect_all(others)) - baseline
        cand = BindingConstraint(cid, float(results[cid].closed_hours), round(gain, 4))
        if best is None or cand.would_extend_window_by_h > best.would_extend_window_by_h or (
            cand.would_extend_window_by_h == best.would_extend_window_by_h
            and cand.hours_lost > best.hours_lost
        ):
            best = cand
    return best


# --------------------------------------------------------------------------- #
# The other five shapes — Day 4. Typed stubs; do not half-build.
# --------------------------------------------------------------------------- #

def evaluate_continuity(series: list[SeriesPoint], spec: ConstraintSpec, ts: list[datetime]) -> ConstraintEvaluation:
    raise NotImplementedError("continuity evaluator")  # Day 4


def evaluate_cure_clock(series: list[SeriesPoint], spec: ConstraintSpec, ts: list[datetime]) -> ConstraintEvaluation:
    raise NotImplementedError("cure_clock evaluator")  # Day 4


def evaluate_composite_rate(series: list[SeriesPoint], spec: ConstraintSpec, ts: list[datetime]) -> ConstraintEvaluation:
    raise NotImplementedError("composite_rate evaluator")  # Day 4


def evaluate_decay_clock(series: list[SeriesPoint], spec: ConstraintSpec, ts: list[datetime]) -> ConstraintEvaluation:
    raise NotImplementedError("decay_clock evaluator")  # Day 4


def evaluate_human(series: list[SeriesPoint], spec: ConstraintSpec, ts: list[datetime]) -> ConstraintEvaluation:
    raise NotImplementedError("human evaluator")  # Day 4
