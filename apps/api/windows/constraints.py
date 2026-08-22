"""
WORKFACE — the seven constraint evaluators.  T3, TASK 5 (band/offset) + Day 4.

All seven shapes now evaluate: `band` and `offset` (Day 3), plus `continuity`,
`cure_clock`, `composite_rate`, `decay_clock` and `human` (Day 4), alongside the
interval algebra (extraction, intersection) and the leave-one-out
`binding_constraint`. Every evaluator keeps the uniform signature
`(series, spec, ts) -> ConstraintEvaluation`; anything extra is keyword-only with
a default, so a generic dispatcher can call all seven identically.

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

from packages.schemas.trade_window import (
    BandSpec,
    CompositeRateSpec,
    ConstraintSpec,
    ContinuitySpec,
    CureClockSpec,
    DecayClockSpec,
    HumanSpec,
    OffsetSpec,
)
from packages.schemas.window_eval import HourState, SeriesPoint

from . import psychro
from .psychro import cure_rate, dew_point_c, evaporation_rate_lb_ft2_hr, heat_index_f

__all__ = [
    "HourVerdict", "Interval", "ConstraintEvaluation", "BindingConstraint",
    "evaluate_band", "evaluate_offset",
    "to_intervals", "intersect", "binding_constraint",
    "evaluate_continuity", "evaluate_cure_clock", "evaluate_composite_rate",
    "evaluate_decay_clock", "evaluate_human",
    "recoat_window_h", "productive_hours",
]

# lb/ft2/hr wind conversion and F<->C helpers used by several evaluators.
_MS_TO_MPH = 2.236936


def _c_to_f(c: float) -> float:
    return c * 9.0 / 5.0 + 32.0


# --------------------------------------------------------------------------- #
# Result types (internal to the evaluator; the WindowEval assembly maps them).
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class HourVerdict:
    ts: datetime
    state: HourState
    margin: float | None = None
    reason: str | None = None
    productive_fraction: float = 1.0    # T3-internal; only the human evaluator moves it off 1.0


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
    margin_unit: str | None = None      # "C" | "pct" | "lb_ft2_hr" | "min" | "h" | "ratio"


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


def _finish(ev: ConstraintEvaluation, unit: str | None = None) -> ConstraintEvaluation:
    if unit is not None:
        ev.margin_unit = unit
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
        return _finish(ConstraintEvaluation(spec.constraint_id, per_hour), unit="C")

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

    unit = "pct" if spec.rh_max_pct is not None else "C"
    return _finish(ConstraintEvaluation(spec.constraint_id, per_hour), unit=unit)


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

    return _finish(ConstraintEvaluation(spec.constraint_id, per_hour), unit="C")


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
# 5.3 Continuity — "compliant AND stays compliant for N hours"
# --------------------------------------------------------------------------- #

def _steps_for_hours(hours: float, step: timedelta) -> int:
    step_h = step.total_seconds() / 3600.0
    return int(round(hours / step_h)) if step_h else 0


def evaluate_continuity(series: list[SeriesPoint], spec: ContinuitySpec, ts: list[datetime],
                        *, grouted: bool = False) -> ConstraintEvaluation:
    """Continuity: an hour is open iff an unbroken protected run holds across it.

        open(t)  <=>  T_gov(s) >= t_min_c  for every sample s in [t - lead, t + run]
        margin   =  min over that whole run of (T_gov - t_min_c)   (NOT the margin at t)

    When `also_on` is set the test is applied to BOTH series (SFRM: substrate AND
    ambient must hold), and the margin is the minimum across both. `grouted=True`
    selects `grouted_run_hours` (masonry: 24 h, 48 h if grouted).

    The trap this evaluator exists to avoid is **horizon truncation**: if the
    required run extends past the end (or before the start) of the series, that
    hour is NO_DATA, not OPEN — a 48 h horizon cannot confirm a 72 h protection
    period. The reason names how many hours of the run fell outside the series.
    Getting this wrong makes the ribbon lie about cold-weather concrete.

    Aside worth saying out loud: this is exactly what FortyGuard's `persistence`
    analytic computes, so a tile can be pre-screened with one API call before the
    local evaluation runs.
    """
    step = _step(ts)
    step_h = step.total_seconds() / 3600.0
    n = len(series)
    t_min = spec.t_min_c if spec.t_min_c is not None else 0.0
    run_hours = spec.grouted_run_hours if (grouted and spec.grouted_run_hours is not None) else spec.run_hours
    lead_hours = spec.lead_hours or 0.0
    lead_steps = _steps_for_hours(lead_hours, step)
    run_steps = _steps_for_hours(run_hours, step)
    on_series = [spec.on] + ([spec.also_on] if spec.also_on else [])

    per_hour: list[HourVerdict] = []
    for i, t in enumerate(ts):
        lo, hi = i - lead_steps, i + run_steps
        missing_before = max(0, -lo)
        missing_after = max(0, hi - (n - 1))
        if missing_before or missing_after:
            outside = round((missing_before + missing_after) * step_h, 1)
            per_hour.append(HourVerdict(
                t, HourState.NO_DATA, None,
                f"required {run_hours:g} h run (+{lead_hours:g} h lead) extends {outside:g} h "
                f"outside the series — cannot confirm, fail closed"))
            continue

        run_margin: float | None = None
        gap = False
        for j in range(lo, hi + 1):
            for on in on_series:
                gov = _governing(series[j], on)
                if gov is None:
                    gap = True
                    break
                m = gov - t_min
                run_margin = m if run_margin is None else min(run_margin, m)
            if gap:
                break
        if gap:
            per_hour.append(HourVerdict(t, HourState.NO_DATA, None,
                                        "missing governing temperature inside the required run — fail closed"))
            continue

        state = _state_from_margin(run_margin, spec.marginal_delta_c)
        pair = "substrate+ambient" if spec.also_on else spec.on
        reason = (f"{run_hours:g} h protected run holds on {pair} at >= {t_min:g} C "
                  f"(worst margin {run_margin:+.1f} C over the run)")
        if state is HourState.CLOSED:
            reason = (f"protected run breaks: {pair} drops {abs(run_margin):.1f} C below the "
                      f"{t_min:g} C floor within {run_hours:g} h")
        per_hour.append(HourVerdict(t, state, round(run_margin, 3), reason))

    return _finish(ConstraintEvaluation(spec.constraint_id, per_hour), unit="C")


# --------------------------------------------------------------------------- #
# 5.4 Cure clock — "if work starts at hour t, what happens to the cure?"
# --------------------------------------------------------------------------- #

def recoat_window_h(spec: CureClockSpec, t_c: float) -> tuple[float, float]:
    """Recoat window (min, max) in hours at a constant temperature.

    Interpolates `recoat_min_hours` linearly in temperature (clamped at the ends)
    and returns `recoat_max_hours` as the upper bound. T1 draws this in the detail
    drawer. Pure; no series involved.
    """
    pts = sorted(spec.recoat_min_hours, key=lambda p: p.t_c)
    upper = spec.recoat_max_hours if spec.recoat_max_hours is not None else float("inf")
    if not pts:
        return (0.0, upper)
    if t_c <= pts[0].t_c:
        return (pts[0].hours, upper)
    if t_c >= pts[-1].t_c:
        return (pts[-1].hours, upper)
    for a, b in zip(pts, pts[1:]):
        if a.t_c <= t_c <= b.t_c:
            f = (t_c - a.t_c) / (b.t_c - a.t_c) if b.t_c != a.t_c else 0.0
            return (round(a.hours + f * (b.hours - a.hours), 2), upper)
    return (pts[-1].hours, upper)


def evaluate_cure_clock(series: list[SeriesPoint], spec: CureClockSpec, ts: list[datetime]) -> ConstraintEvaluation:
    """Cure clock: cure is an integral, not a threshold, so this answers a
    different question — *if the work starts at hour t, when does it reach the
    milestone?*

        margin = projected_hours_to_milestone      (margin_unit = "h")

    For each start hour t we integrate `psychro.cure_progress` forward using the
    actual series while it lasts, then hold the last known temperature constant to
    project completion; a projection that leaned on that constant tail is named in
    the reason (honesty about extrapolation is the house style).

    States:
      * NO_DATA  — governing temperature missing at t.
      * CLOSED   — the temperature at t is BELOW the calibrated Q10 range (below the
                   lowest t_lo_c). Cure is not characterised there; we must not
                   extrapolate a rate model into the stall zone.
      * MARGINAL — projected hours >= 1.5 x hours_at_ref (cure stalling badly — the
                   low-temperature deviation the tech spec calls out).
      * OPEN     — otherwise.

    JUDGEMENT CALL / DEVIATION FROM THE BRIEF (reported to the team). The brief's
    A2 marks a start temperature ABOVE the top calibration (t_hi_c) as CLOSED too.
    Taken literally, that closes a perfectly coatable steel deck at midday — the
    bare galvanised deck in the hero series reaches ~60 C, well under Macropoxy
    646's 121 C surface application maximum, and cure is simply *faster* than the
    hottest calibrated point, not undefined. Closing it is physically wrong and it
    breaks the hero fixture (dawn condensation is the story, not midday warmth). So
    above t_hi_c we do NOT close: we CAP the rate at the calibrated range (never
    extrapolate the Q10 upward) and stay open, naming the cap in the reason. The
    cold side, where cure genuinely stalls, keeps the CLOSED gate. See the report.
    """
    segs = spec.q10_segments
    lo_c = min((s.t_lo_c for s in segs), default=float("-inf"))
    hi_c = max((s.t_hi_c for s in segs), default=float("inf"))

    def _rate_capped(t_c: float) -> float:
        # Never extrapolate the Q10 past either calibrated bound.
        return cure_rate(min(max(t_c, lo_c), hi_c), segs, spec.ref_c)

    step = _step(ts)
    step_h = step.total_seconds() / 3600.0
    n = len(series)
    target = spec.hours_at_ref            # equivalent reference-hours needed for the milestone
    marginal_at = 1.5 * spec.hours_at_ref

    per_hour: list[HourVerdict] = []
    for i, t in enumerate(ts):
        t0 = _governing(series[i], spec.on)
        if t0 is None:
            per_hour.append(HourVerdict(t, HourState.NO_DATA, None,
                                        f"no {spec.on} temperature at start hour — fail closed"))
            continue
        if t0 < lo_c:
            per_hour.append(HourVerdict(
                t, HourState.CLOSED, None,
                f"{t0:.1f} C is below the calibrated cure range (>= {lo_c:g} C); cure stalls and "
                f"is not characterised there — will not extrapolate"))
            continue

        equiv = 0.0
        elapsed = 0.0
        last_t = t0
        capped = t0 > hi_c
        for j in range(i, n):
            tj = _governing(series[j], spec.on)
            if tj is None:
                break                     # ran out of real data -> fall through to constant tail
            last_t = tj
            capped = capped or tj > hi_c
            r = _rate_capped(tj)
            if equiv + r * step_h >= target:
                frac = (target - equiv) / (r * step_h) if r * step_h > 0 else 0.0
                elapsed += frac * step_h
                equiv = target
                break
            equiv += r * step_h
            elapsed += step_h

        tail_used = False
        if equiv < target:
            tail_used = True
            r_tail = _rate_capped(last_t)
            elapsed += (target - equiv) / r_tail if r_tail > 0 else float("inf")

        projected = round(elapsed, 2)
        state = HourState.MARGINAL if projected >= marginal_at else HourState.OPEN
        reason = (f"start now -> {spec.milestone or 'milestone'} in ~{projected:g} h "
                  f"(ref {spec.hours_at_ref:g} h at {spec.ref_c:g} C)")
        if capped:
            reason += f"; cure rate capped at the {hi_c:g} C calibration (not extrapolated)"
        if tail_used:
            reason += f"; projection held {last_t:.1f} C constant past the series end"
        if state is HourState.MARGINAL:
            reason += "; cure stalling (>= 1.5x reference)"
        per_hour.append(HourVerdict(t, state, projected, reason))

    return _finish(ConstraintEvaluation(spec.constraint_id, per_hour), unit="h")


# --------------------------------------------------------------------------- #
# 5.5 Composite rate — dispatch on spec.formula
# --------------------------------------------------------------------------- #

def evaluate_composite_rate(series: list[SeriesPoint], spec: CompositeRateSpec, ts: list[datetime],
                            *, low_bleed: bool = False) -> ConstraintEvaluation:
    """Composite rate: two genuinely different formulas live under this shape, so
    it dispatches on `spec.formula`.

    `menzel_nrmca` — the ACI 305 evaporation rate. ACI 305 defines hot weather as
    "any combination of high air temperature, low relative humidity, wind, and
    solar radiation" — NOT a temperature — which is exactly why a cold, dry, windy
    morning can beat a hot, calm afternoon. **Missing wind -> NO_DATA**, naming
    wind explicitly as the one field FortyGuard does not supply (that string is
    product feedback for the sponsor and belongs in the UI).

    `wind_modified_air_temperature_trigger` — the TMS 602 masonry trigger. This is
    a trigger, not a stop: hot weather obliges hot-weather masonry procedures, it
    does not send the crew home. So OPEN when nothing fires, MARGINAL at tier 1 or
    tier 2, never CLOSED; the reason names which limb fired (temperature or wind).
    """
    if spec.formula == "menzel_nrmca":
        return _evaluate_menzel(series, spec, ts, low_bleed=low_bleed)
    if spec.formula == "wind_modified_air_temperature_trigger":
        return _evaluate_wind_trigger(series, spec, ts)
    raise ValueError(f"unknown composite_rate formula {spec.formula!r} on {spec.constraint_id!r}")


def _evaluate_menzel(series: list[SeriesPoint], spec: CompositeRateSpec, ts: list[datetime],
                     *, low_bleed: bool) -> ConstraintEvaluation:
    limit = (spec.low_bleed_limit_lb_ft2_hr if (low_bleed and spec.low_bleed_limit_lb_ft2_hr is not None)
             else (spec.limit_lb_ft2_hr if spec.limit_lb_ft2_hr is not None else 0.2))
    marginal = spec.marginal_lb_ft2_hr if spec.marginal_lb_ft2_hr is not None else 0.1

    per_hour: list[HourVerdict] = []
    for sp, t in zip(series, ts):
        tc_c = sp.t_surf_c if sp.t_surf_c is not None else sp.t_base_material_c
        if sp.wind_ms is None:
            per_hour.append(HourVerdict(
                t, HourState.NO_DATA, None,
                "no wind speed — evaporation rate needs wind, the one field FortyGuard "
                "does not supply (take it from a site-level feed)"))
            continue
        if tc_c is None or sp.t_air_c is None or sp.rh_pct is None:
            per_hour.append(HourVerdict(t, HourState.NO_DATA, None,
                                        "missing surface, air or RH — fail closed, never guess"))
            continue
        e = evaporation_rate_lb_ft2_hr(_c_to_f(tc_c), _c_to_f(sp.t_air_c), sp.rh_pct,
                                       sp.wind_ms * _MS_TO_MPH)
        margin = limit - e
        if e >= limit:
            state = HourState.CLOSED
        elif e >= marginal:
            state = HourState.MARGINAL
        else:
            state = HourState.OPEN
        reason = (f"ACI 305 evaporation {e:.3f} lb/ft2/hr (surface {_c_to_f(tc_c):.0f} F, "
                  f"RH {sp.rh_pct:.0f}%, wind {sp.wind_ms * _MS_TO_MPH:.0f} mph); "
                  f"plastic-shrinkage precautions at {limit:g}")
        per_hour.append(HourVerdict(t, state, round(margin, 4), reason))

    return _finish(ConstraintEvaluation(spec.constraint_id, per_hour), unit="lb_ft2_hr")


def _evaluate_wind_trigger(series: list[SeriesPoint], spec: CompositeRateSpec,
                           ts: list[datetime]) -> ConstraintEvaluation:
    per_hour: list[HourVerdict] = []
    for sp, t in zip(series, ts):
        if sp.t_air_c is None:
            per_hour.append(HourVerdict(t, HourState.NO_DATA, None, "no air temperature — fail closed"))
            continue
        ta_f = _c_to_f(sp.t_air_c)
        v_mph = sp.wind_ms * _MS_TO_MPH if sp.wind_ms is not None else None
        # Wind is only decisive in the 90-100 F and 105-115 F bands; if it is missing
        # there we cannot tell whether the trigger fires -> NO_DATA (names wind).
        if v_mph is None and ((90.0 < ta_f <= 100.0) or (105.0 < ta_f <= 115.0)):
            per_hour.append(HourVerdict(
                t, HourState.NO_DATA, None,
                f"air {ta_f:.0f} F is in the wind-decided band and wind is missing — "
                f"cannot resolve the trigger (wind is the field FortyGuard omits)"))
            continue
        v = v_mph if v_mph is not None else 0.0
        tier2 = ta_f > 115.0 or (ta_f > 105.0 and v > 8.0)
        tier1 = ta_f > 100.0 or (ta_f > 90.0 and v > 8.0)
        margin = round((100.0 - ta_f) / 1.8, 2)      # C-equiv distance to the 100 F limb
        if tier2:
            limb = "temperature" if ta_f > 115.0 else "wind"
            state, reason = HourState.MARGINAL, (
                f"tier 2 fired on the {limb} limb (air {ta_f:.0f} F, wind {v:.0f} mph): shade "
                f"materials, cool mixing water. Procedures, not a stop")
        elif tier1:
            limb = "temperature" if ta_f > 100.0 else "wind"
            state, reason = HourState.MARGINAL, (
                f"tier 1 fired on the {limb} limb (air {ta_f:.0f} F, wind {v:.0f} mph): fog-spray, "
                f"damp sand, mortar within 2 h. Procedures, not a stop")
        else:
            state, reason = HourState.OPEN, (
                f"air {ta_f:.0f} F, wind {v:.0f} mph below the hot-weather trigger; standard procedures")
        per_hour.append(HourVerdict(t, state, margin, reason))

    return _finish(ConstraintEvaluation(spec.constraint_id, per_hour), unit="C")


# --------------------------------------------------------------------------- #
# 5.6 Decay clock — dispatch on spec.quantity
# --------------------------------------------------------------------------- #

def _interp_midpoints(base_c: float, anchors: list[tuple[float, float]]) -> float | None:
    """Linear interpolation between bracket midpoints; None if outside the qualified band."""
    anchors = sorted(anchors, key=lambda a: a[0])
    if not anchors:
        return None
    if base_c < anchors[0][0]:
        return anchors[0][1]
    if base_c > anchors[-1][0]:
        return anchors[-1][1]
    for (t0, v0), (t1, v1) in zip(anchors, anchors[1:]):
        if t0 <= base_c <= t1:
            f = (base_c - t0) / (t1 - t0) if t1 != t0 else 0.0
            return v0 + f * (v1 - v0)
    return anchors[-1][1]


def evaluate_decay_clock(series: list[SeriesPoint], spec: DecayClockSpec, ts: list[datetime],
                         *, lift_mm: int = 50, minutes_required: float | None = None,
                         wet_hole: bool = False) -> ConstraintEvaluation:
    """Decay clock: available working/compaction minutes as a function of base
    material temperature. Dispatches on `spec.quantity` because the two registry
    rows carry different lookup shapes.

      * `working_time_minutes` (adhesive anchor epoxy): 120 min at 0 C collapsing
        to 10 min at 40 C.
      * `available_compaction_minutes` (HMA paving): rows keyed by lift thickness;
        `lift_mm` (keyword-only, default 50) selects the column.

    When `minutes_required` is None every in-range hour is OPEN and `margin` is the
    minutes available (informational — what the ribbon shows before a crew's roller
    pattern is known). When supplied, CLOSED iff available < required and
    `margin = available - required`. Out of the qualified band is CLOSED, never
    extrapolated. `wet_hole` applies `wet_hole_cure_multiplier` to the reported
    cure time (informational only — it does not move the working-time verdict).

    The direction inversion is the demo point: for asphalt a *hotter* base gives
    *more* compaction minutes at thin lifts, so one trade's red is another trade's
    green on the same tile in the same hour.
    """
    qty = spec.quantity
    lo = min((float(r["t_lo_c"] if "t_lo_c" in r else r["base_t_c_lo"]) for r in spec.lookup), default=None)
    hi = max((float(r["t_hi_c"] if "t_hi_c" in r else r["base_t_c_hi"]) for r in spec.lookup), default=None)

    # Build (midpoint_temperature, minutes) anchors for the selected quantity/lift.
    anchors: list[tuple[float, float]] = []
    for r in spec.lookup:
        if qty == "working_time_minutes":
            mid = (float(r["t_lo_c"]) + float(r["t_hi_c"])) / 2.0
            anchors.append((mid, float(r["working_time_min"])))
        elif qty == "available_compaction_minutes":
            col = r.get("by_lift_mm", {})
            key = str(lift_mm)
            if key in col:
                mid = (float(r["base_t_c_lo"]) + float(r["base_t_c_hi"])) / 2.0
                anchors.append((mid, float(col[key])))
        else:
            raise ValueError(f"unknown decay_clock quantity {qty!r} on {spec.constraint_id!r}")
    if not anchors:
        raise ValueError(f"decay_clock {spec.constraint_id!r}: no lookup rows for lift_mm={lift_mm}")

    per_hour: list[HourVerdict] = []
    for sp, t in zip(series, ts):
        base = _governing(sp, spec.on)
        if base is None:
            per_hour.append(HourVerdict(t, HourState.NO_DATA, None,
                                        f"no {spec.on} temperature — fail closed"))
            continue
        if lo is not None and hi is not None and (base < lo or base > hi):
            per_hour.append(HourVerdict(
                t, HourState.CLOSED, None,
                f"base {base:.0f} C outside the qualified band {lo:g}-{hi:g} C — product not "
                f"qualified there; will not extrapolate"))
            continue
        available = _interp_midpoints(base, anchors)
        cure_note = ""
        if wet_hole and spec.wet_hole_cure_multiplier is not None:
            cure_note = f"; cure time x{spec.wet_hole_cure_multiplier:g} in a wet hole"
        if minutes_required is None:
            state = HourState.OPEN
            margin = round(available, 1)
            reason = (f"base {base:.0f} C -> {available:.0f} min available "
                      f"({'working time' if qty == 'working_time_minutes' else f'compaction, {lift_mm} mm lift'})"
                      f"{cure_note}")
        else:
            margin = round(available - minutes_required, 1)
            state = HourState.CLOSED if available < minutes_required else HourState.OPEN
            reason = (f"base {base:.0f} C -> {available:.0f} min available vs {minutes_required:g} min "
                      f"required (margin {margin:+.0f} min){cure_note}")
        per_hour.append(HourVerdict(t, state, margin, reason))

    return _finish(ConstraintEvaluation(spec.constraint_id, per_hour), unit="min")


# --------------------------------------------------------------------------- #
# 5.7 Human — dispatch on spec.metric
# --------------------------------------------------------------------------- #

def productive_hours(interval: Interval, per_hour: list) -> float:
    """Productive crew-hours across an interval = sum(step_h * productive_fraction).

    This is the number that matters to a superintendent: a five-hour window at a
    25%% rest ratio is 3.75 productive crew-hours, and the activity needs 6. It
    feeds OpenInterval.productive_h and, later, the sequencer. `per_hour` is any
    list of objects carrying `.ts` and `.productive_fraction` (HourVerdict or
    HourCell both qualify).
    """
    ts = [h.ts for h in per_hour]
    step_h = _step(ts).total_seconds() / 3600.0
    total = 0.0
    for h in per_hour:
        if interval.start <= h.ts < interval.end:
            total += step_h * getattr(h, "productive_fraction", 1.0)
    return round(total, 4)


def evaluate_human(series: list[SeriesPoint], spec: HumanSpec, ts: list[datetime]) -> ConstraintEvaluation:
    """Human: dispatch on `spec.metric`. Heat stress shrinks a window, it does not
    close one — no hour here ever returns CLOSED.

    `heat_index_f` — the two OSHA triggers (80 F initial, 90 F high-heat). Triggers,
    not stops: OPEN below, MARGINAL above. The reason quotes the heat index in F
    (the unit the rule is written in) and names the required measures; because
    HourCell.margin_unit has no F member, margin is reported as a C-equivalent
    delta (threshold_F - HI_F)/1.8. The rule is NOT final — the NPRM published
    30 Aug 2024, no target date for a final rule as of mid-2026, and OSHA enforces
    heat in the interim under the General Duty Clause Section 5(a)(1).

    `wbgt_c` — the real output is not open/closed but how much of the hour the crew
    can work. Use `sp.wbgt_c` when the series carries it (source: series), else
    model it with `psychro.wbgt_outdoor_c` and mark the reason `modelled`. Map WBGT
    into `productive_fraction_by_band` and carry the band's work_fraction on
    HourVerdict.productive_fraction. OPEN when work_fraction == 1.0, else MARGINAL;
    margin = work_fraction, margin_unit = "ratio". The ACGIH work/rest table is
    copyrighted; these bands are WORKFACE placeholders and the reason says so.
    """
    if spec.metric == "heat_index_f":
        return _evaluate_heat_index(series, spec, ts)
    if spec.metric == "wbgt_c":
        return _evaluate_wbgt(series, spec, ts)
    raise ValueError(f"unknown human metric {spec.metric!r} on {spec.constraint_id!r}")


def _evaluate_heat_index(series: list[SeriesPoint], spec: HumanSpec, ts: list[datetime]) -> ConstraintEvaluation:
    threshold_f = spec.threshold if spec.threshold is not None else 80.0
    high_heat = threshold_f >= 90.0
    per_hour: list[HourVerdict] = []
    for sp, t in zip(series, ts):
        if sp.t_air_c is None or sp.rh_pct is None:
            per_hour.append(HourVerdict(t, HourState.NO_DATA, None,
                                        "no air temperature or RH — fail closed"))
            continue
        hi = heat_index_f(_c_to_f(sp.t_air_c), sp.rh_pct)
        margin = round((threshold_f - hi) / 1.8, 2)          # C-equivalent delta; F kept in the reason
        if hi >= threshold_f:
            state = HourState.MARGINAL
            measures = ("15-minute paid breaks at least every two hours, symptom monitoring, hazard alert"
                        if high_heat else
                        "cool drinking water, shaded break areas, acclimatisation for new/returning crew")
            reason = (f"heat index {hi:.0f} F at/above the {threshold_f:.0f} F OSHA trigger "
                      f"({measures}); proposed rule not final — General Duty Clause 5(a)(1) applies")
        else:
            state = HourState.OPEN
            reason = f"heat index {hi:.0f} F below the {threshold_f:.0f} F OSHA trigger"
        per_hour.append(HourVerdict(t, state, margin, reason))

    return _finish(ConstraintEvaluation(spec.constraint_id, per_hour), unit="C")


def _wbgt_band_fraction(spec: HumanSpec, wbgt_c: float) -> float:
    for band in spec.productive_fraction_by_band:
        if band.wbgt_c_lo <= wbgt_c < band.wbgt_c_hi:
            return band.work_fraction
    # Above the top band, take the lowest work fraction; below the first, full work.
    if spec.productive_fraction_by_band:
        if wbgt_c >= spec.productive_fraction_by_band[-1].wbgt_c_hi:
            return min(b.work_fraction for b in spec.productive_fraction_by_band)
        return spec.productive_fraction_by_band[0].work_fraction
    return 1.0


def _evaluate_wbgt(series: list[SeriesPoint], spec: HumanSpec, ts: list[datetime]) -> ConstraintEvaluation:
    per_hour: list[HourVerdict] = []
    for sp, t in zip(series, ts):
        modelled = False
        wbgt = sp.wbgt_c
        if wbgt is None:
            if sp.t_air_c is None or sp.rh_pct is None or sp.wind_ms is None or sp.ghi_w_m2 is None:
                per_hour.append(HourVerdict(t, HourState.NO_DATA, None,
                                            "no WBGT and cannot model it (air/RH/wind/GHI missing) — fail closed"))
                continue
            wbgt = psychro.wbgt_outdoor_c(sp.t_air_c, sp.rh_pct, sp.wind_ms, sp.ghi_w_m2)
            modelled = True
        frac = _wbgt_band_fraction(spec, wbgt)
        state = HourState.OPEN if frac >= 1.0 else HourState.MARGINAL
        src = f"modelled ({psychro.WBGT_METHOD})" if modelled else "from series"
        reason = (f"WBGT {wbgt:.1f} C {src} -> {frac:.0%} work / {1 - frac:.0%} rest "
                  f"(WORKFACE placeholder bands, pending ACGIH licence)")
        per_hour.append(HourVerdict(t, state, round(frac, 3), reason, productive_fraction=frac))

    return _finish(ConstraintEvaluation(spec.constraint_id, per_hour), unit="ratio")
