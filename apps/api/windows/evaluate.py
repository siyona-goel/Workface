"""
WORKFACE — the assembly: seven evaluators -> one WindowEval.  T3, TASK 6 (Day 4).

`evaluate_window` dispatches every constraint spec of a trade to its evaluator,
folds the per-constraint results into the dense hour ribbon T1 renders, and rolls
them up into the single `WindowEval` object that is handoff #5 to T1.

Pure Python over an in-memory series. No I/O beyond the cached registry loader, no
network, no LLM. The physics is the unit-tested code in constraints.py / psychro.py;
this module only orchestrates and narrates.

# ---------------------------------------------------------------------------
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task (from P6 / the generator)
#   fg_activity_id  = a FortyGuard async job handle (from submit -> /v1/status/{id})
# ---------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

from packages.schemas.trade_window import ConstraintSpec, TradeWindow
from packages.schemas.window_eval import (
    BindingConstraint,
    Confidence,
    ConstraintResult,
    ConstraintType,
    GoverningTemp,
    Horizon,
    HourCell,
    HourState,
    Margin,
    OpenInterval,
    Provenance,
    ScheduledBar,
    SeriesPoint,
    UsdExposure,
    Verdict,
    WindowEval,
)

from . import constraints as C
from .constraints import ConstraintEvaluation, Interval
from .registry import Registry, load_registry

# spec.type -> evaluator. A missing type must raise, not silently skip.
_DISPATCH = {
    "band": C.evaluate_band,
    "offset": C.evaluate_offset,
    "continuity": C.evaluate_continuity,
    "cure_clock": C.evaluate_cure_clock,
    "composite_rate": C.evaluate_composite_rate,
    "decay_clock": C.evaluate_decay_clock,
    "human": C.evaluate_human,
}

# Worst-first ordering of hour states. A single closed constraint closes the hour;
# with nothing closed, a constraint that cannot be confirmed (NO_DATA) fails closed
# ahead of a merely marginal one.
_STATE_RANK = {
    HourState.CLOSED: 3,
    HourState.NO_DATA: 2,
    HourState.MARGINAL: 1,
    HourState.OPEN: 0,
}


def _gov_temp(spec: ConstraintSpec, trade: TradeWindow) -> GoverningTemp:
    on = getattr(spec, "on", None)
    try:
        return GoverningTemp(on) if on is not None else trade.governing_temp
    except ValueError:
        return trade.governing_temp


def _series_digest(series: list[SeriesPoint]) -> str:
    canonical = json.dumps([sp.model_dump(mode="json") for sp in series],
                           sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _pick_binding_for_hour(state: HourState,
                           at: list[tuple[str, C.HourVerdict, ConstraintEvaluation]]
                           ) -> tuple[str, C.HourVerdict, ConstraintEvaluation] | None:
    """Which constraint set this cell's state (and, when open, which is tightest)."""
    if state is HourState.OPEN:
        # No binding id for an open hour, but surface the tightest constraint's reason.
        pos = [x for x in at if x[1].margin is not None]
        return min(pos, key=lambda x: x[1].margin) if pos else (at[0] if at else None)
    matching = [x for x in at if x[1].state is state]
    if not matching:
        return at[0] if at else None
    if state in (HourState.CLOSED, HourState.MARGINAL):
        withm = [x for x in matching if x[1].margin is not None]
        if withm:
            return min(withm, key=lambda x: x[1].margin)   # most binding = smallest margin
    return matching[0]


def _open_intervals(cells: list[HourCell],
                    results: dict[str, ConstraintEvaluation],
                    confidence: Confidence) -> list[OpenInterval]:
    """Intersection of every constraint's usable (open+marginal) intervals."""
    if not results:
        return []
    ts = [c.ts for c in cells]
    step = C._step(ts)
    horizon = [Interval(ts[0], ts[-1] + step, True)] if ts else []
    acc = horizon
    for ev in results.values():
        acc = C.intersect(acc, C.to_intervals(ev.per_hour, include_marginal=True))

    out: list[OpenInterval] = []
    for iv in acc:
        inside = [c for c in cells if iv.start <= c.ts < iv.end]
        margins = [c.margin for c in inside if c.margin is not None]
        out.append(OpenInterval(
            start=iv.start,
            end=iv.end,
            duration_h=iv.duration_h,
            productive_h=C.productive_hours(iv, inside),
            includes_marginal=any(c.state is HourState.MARGINAL for c in inside),
            min_margin=round(min(margins), 3) if margins else None,
            confidence=confidence,
        ))
    return out


def _confidence(series: list[SeriesPoint], trade: TradeWindow) -> tuple[Confidence, list[str]]:
    gov_on = trade.governing_temp.value
    present = sum(1 for sp in series if C._governing(sp, gov_on) is not None)
    total = len(series)
    if total and present == total:
        return Confidence.HIGH, [f"governing ({gov_on}) temperature present for all {total} hours"]
    if present:
        return Confidence.MEDIUM, [
            f"governing ({gov_on}) temperature missing for {total - present} of {total} hours — "
            f"twin degraded, treat thin-margin hours with care"]
    return Confidence.LOW, [f"no governing ({gov_on}) temperature — climatology-backed only"]


def _verdict(bar_states: list[HourState], open_intervals: list[OpenInterval],
             scheduled: ScheduledBar) -> Verdict:
    if not bar_states or any(s is HourState.NO_DATA for s in bar_states):
        return Verdict.NO_DATA
    if all(s is HourState.CLOSED for s in bar_states):
        return Verdict.NON_COMPLIANT
    covered = any(iv.start <= scheduled.start and iv.end >= scheduled.finish for iv in open_intervals)
    if all(s is HourState.OPEN for s in bar_states) and covered:
        return Verdict.COMPLIANT
    longest = max((iv.duration_h for iv in open_intervals), default=0.0)
    if longest + 1e-9 < scheduled.duration_h:
        return Verdict.INSUFFICIENT_WINDOW
    return Verdict.AT_RISK


def _mitigation_hint(trade: TradeWindow) -> str | None:
    if not trade.mitigations:
        return None
    return ", ".join(m.replace("_", " ") for m in trade.mitigations[:2])


def evaluate_window(
    *,
    trade_id: str,
    series: list[SeriesPoint],
    ts: list[datetime],
    scheduled: ScheduledBar,
    activity_id: str,
    activity_name: str,
    work_face_id: str,
    work_face_name: str,
    run_id: str,
    trade_display_name: str | None = None,
    wbs: str | None = None,
    generated_at: datetime | None = None,
    horizon: Horizon | None = None,
    fg_activity_ids: list[str] | None = None,
    registry: Registry | None = None,
) -> WindowEval:
    """Evaluate one activity over one horizon and return the WindowEval T1 renders.

    `series` and `ts` are parallel and dense (one entry per horizon step). The
    trade's constraints are loaded through the registry (never re-parsed) and each
    is dispatched to its evaluator; a spec whose `type` has no evaluator raises.
    """
    if len(series) != len(ts):
        raise ValueError(f"series ({len(series)}) and ts ({len(ts)}) must be parallel")
    if not ts:
        raise ValueError("empty horizon — nothing to evaluate")

    reg = registry or load_registry()
    trade = reg.get(trade_id)
    step = C._step(ts)

    # 1-2. Dispatch every spec to its evaluator.
    results: dict[str, ConstraintEvaluation] = {}
    specs: dict[str, ConstraintSpec] = {}
    for spec in trade.constraints:
        fn = _DISPATCH.get(spec.type)
        if fn is None:
            raise ValueError(f"no evaluator for constraint type {spec.type!r} ({spec.constraint_id})")
        results[spec.constraint_id] = fn(series, spec, ts)
        specs[spec.constraint_id] = spec

    # 3. Dense hour ribbon: worst state per hour + the binding constraint for THAT hour.
    cells: list[HourCell] = []
    for i, t in enumerate(ts):
        at = [(cid, ev.per_hour[i], ev) for cid, ev in results.items()]
        state = max((x[1].state for x in at), key=lambda s: _STATE_RANK[s], default=HourState.OPEN)
        pick = _pick_binding_for_hour(state, at)
        pf = min((x[1].productive_fraction for x in at), default=1.0)
        binding_id = None if state is HourState.OPEN else (pick[0] if pick else None)
        margin = pick[1].margin if pick else None
        unit = pick[2].margin_unit if pick else None
        reason = pick[1].reason if pick else None
        cells.append(HourCell(
            ts=t,
            state=state,
            binding_constraint_id=binding_id,
            margin=margin,
            margin_unit=unit if margin is not None else None,
            reason=(reason or "")[:240] or None,
            productive_fraction=pf,
            values=series[i],
        ))

    conf, conf_reasons = _confidence(series, trade)

    # 4. Open intervals = intersection of every constraint's usable intervals.
    open_intervals = _open_intervals(cells, results, conf)

    # 5. Per-constraint breakdown.
    cres: list[ConstraintResult] = []
    for cid, ev in results.items():
        spec = specs[cid]
        opens = [h.ts for h in ev.per_hour if h.state is HourState.OPEN]
        cres.append(ConstraintResult(
            constraint_id=cid,
            type=ConstraintType(spec.type),
            label=spec.label,
            governing_temp=_gov_temp(spec, trade),
            satisfied_hours=ev.satisfied_hours,
            closed_hours=ev.closed_hours,
            first_open=opens[0] if opens else None,
            last_open=opens[-1] if opens else None,
            worst_margin=ev.worst_margin,
            margin_unit=ev.margin_unit,  # type: ignore[arg-type]
            citation_fragment=spec.citation_fragment,
        ))

    # 6. Binding constraint via leave-one-out, dressed with type/label/mitigation.
    binding_internal = C.binding_constraint(results)
    binding = None
    if binding_internal is not None:
        bspec = specs[binding_internal.constraint_id]
        binding = BindingConstraint(
            constraint_id=binding_internal.constraint_id,
            type=ConstraintType(bspec.type),
            label=bspec.label,
            hours_lost=binding_internal.hours_lost,
            would_extend_window_by_h=binding_internal.would_extend_window_by_h,
            mitigation_hint=_mitigation_hint(trade),
        )

    # 7. Verdict against the scheduled bar.
    bar_states = [c.state for c in cells if scheduled.start <= c.ts < scheduled.finish]
    verdict = _verdict(bar_states, open_intervals, scheduled)

    # 8. Margin: the binding constraint's worst value inside the bar (else overall).
    margin_model = None
    if binding is not None:
        bev = results[binding.constraint_id]
        in_bar = [h for h in bev.per_hour
                  if scheduled.start <= h.ts < scheduled.finish and h.margin is not None]
        pool = in_bar or [h for h in bev.per_hour if h.margin is not None]
        if pool and bev.margin_unit is not None:
            worst = min(pool, key=lambda h: h.margin)
            margin_model = Margin(value=round(worst.margin, 3),
                                  unit=bev.margin_unit,  # type: ignore[arg-type]
                                  at=worst.ts)

    # 9. Verdict summary — names the clause and the hours, <= 400 chars.
    summary = _summary(trade, verdict, open_intervals, scheduled, binding)

    # 10. USD exposure.
    usd = _usd_exposure(trade, verdict)

    # 12. Provenance.
    prov = Provenance(
        fg_activity_ids=list(fg_activity_ids or []),
        series_digest=_series_digest(series),
        registry_version=reg.version,
        twin_confidence=conf,
        replay=True,
    )

    if horizon is None:
        horizon = Horizon(start=ts[0], end=ts[-1] + step,
                          step_minutes=int(step.total_seconds() // 60), tier="commit")

    return WindowEval(
        run_id=run_id,
        generated_at=generated_at or ts[0],
        activity_id=activity_id,
        activity_name=activity_name,
        wbs=wbs,
        trade_id=trade_id,
        trade_display_name=trade_display_name or trade.display_name,
        work_face_id=work_face_id,
        work_face_name=work_face_name,
        horizon=horizon,
        scheduled=scheduled,
        hours=cells,
        open_intervals=open_intervals,
        constraints=cres,
        binding_constraint=binding,
        margin=margin_model,
        verdict=verdict,
        verdict_summary=summary,
        citation=trade.citation,
        standard_ref=trade.standard_ref,
        usd_exposure=usd,
        confidence=conf,
        confidence_reasons=conf_reasons,
        provenance=prov,
    )


def _summary(trade: TradeWindow, verdict: Verdict, open_intervals: list[OpenInterval],
             scheduled: ScheduledBar, binding: BindingConstraint | None) -> str:
    dur = scheduled.duration_h
    clause = binding.label if binding is not None else trade.display_name
    if verdict is Verdict.NO_DATA:
        s = (f"{trade.display_name}: insufficient data over the scheduled bar — fail closed, "
             f"no verdict issued. Binding: {clause}.")
    elif verdict is Verdict.NON_COMPLIANT:
        s = (f"{trade.display_name}: the {dur:g} h bar at {scheduled.start:%H:%M} sits on closed "
             f"hours. Binding constraint: {clause}.")
    elif verdict is Verdict.INSUFFICIENT_WINDOW:
        longest = max((iv.duration_h for iv in open_intervals), default=0.0)
        s = (f"{trade.display_name}: longest open window is {longest:g} h against a {dur:g} h "
             f"activity — no compliant slot. Binding constraint: {clause}.")
    else:
        best = max(open_intervals, key=lambda iv: iv.duration_h, default=None)
        if best is not None:
            window = f"{best.start:%H:%M}–{best.end:%H:%M} ({best.duration_h:g} h open"
            if best.productive_h + 1e-6 < best.duration_h:
                window += f", {best.productive_h:g} h productive after the WBGT haircut"
            window += ")"
        else:
            window = "no open interval"
        verb = "sits inside" if verdict is Verdict.COMPLIANT else "clips"
        s = (f"{trade.display_name}: {dur:g} h bar at {scheduled.start:%H:%M} {verb} the window "
             f"{window}. Binding constraint: {clause}.")
    return s[:400]


def _usd_exposure(trade: TradeWindow, verdict: Verdict) -> UsdExposure:
    uc, qty, rw = trade.unit_cost_usd, trade.typical_quantity, trade.rework_multiplier
    if uc is None or qty is None or rw is None:
        return UsdExposure(at_risk_usd=0.0, protected_usd=0.0,
                           basis="no unit cost / quantity / rework multiplier in the registry row")
    exposure = round(uc * qty * rw, 0)
    basis = (f"quantity {qty:g} {trade.unit or 'unit'} x ${uc:g}/{trade.unit or 'unit'} "
             f"x rework multiplier {rw:g}")
    if verdict is Verdict.COMPLIANT:
        return UsdExposure(at_risk_usd=0.0, protected_usd=exposure, basis=basis)
    return UsdExposure(at_risk_usd=exposure, protected_usd=0.0, basis=basis)


__all__ = ["evaluate_window"]
