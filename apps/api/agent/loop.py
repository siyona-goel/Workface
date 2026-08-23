"""
WORKFACE — agent loop v1: SCAN -> EVALUATE -> CONFLICT.  T3, Day 6, Task E.

    from apps.api.agent.loop import run_agent
    run = run_agent()          # -> a real AgentRun (agent_trace.py schema)

Three stages ONLY (WORKFACE_TECH_SPEC §8.1, first half):

    SCAN     -> list_activities_in_lookahead(72) over the demo activities
    EVALUATE -> get_work_face_thermal -> evaluate_window   [deterministic]
    CONFLICT -> group by work face + shift; emit a Conflict wherever
                demanded_hours > compliant_hours

No PROPOSE, no GATE, no ACT, no LLM — those are Day 7+. THE GATE IS PURE PYTHON;
a model problem cannot block this. The physics and the window maths are the
existing, unit-tested `evaluate_window`; the agent CALLS it, it does not
reimplement it (§8.2).

    demanded_hours sums PRODUCTIVE hours (post-WBGT haircut) via
    `constraints.productive_hours` — exactly what that helper was written for.
    compliant_hours is the open clock-hours available on the face that shift.

The emitted AgentRun is the SAME schema as the hand-written
`data/fixtures/sample_agent_run.json`, so T1's Trace view — built against that
fixture today — renders this live output with no changes. This loop writes to a
NEW path (scripts/make_agent_run_live.py); it NEVER overwrites the fixture T1 is
building against.

Lookahead anchor: the demo window start 2026-08-24T00:00 (the same 72 h horizon
the thermal bundle covers), with OVERLAP semantics (an activity is in the
lookahead if its planned window intersects the horizon) — which is what makes the
count 62 in-window / 37 thermal-sensitive.

# ---------------------------------------------------------------------------
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task (from P6 / the generator)
#   fg_activity_id  = a FortyGuard async job handle (from submit -> /v1/status/{id})
# ---------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from apps.api.agent.llm import get_model, is_configured
from apps.api.agent.policy import load_policy
from apps.api.agent.propose import Attempt, resolve_activity, strategy_order_for
from apps.api.sequencer.pack import YamlCrewSource
from apps.api.sitefeeds.sitesystems import MockSiteSystems
from apps.api.windows import constraints as C
from apps.api.windows.evaluate import evaluate_window
from apps.api.windows.registry import load_registry
from packages.schemas.agent_trace import (
    AgentRun,
    AgentStep,
    Conflict,
    GateVerdict,
    Proposal,
    ProposalKind,
    RunStatus,
    StepType,
    ToolCall,
    ToolName,
)
from packages.schemas.thermal_series import ThermalSeriesBundle, WorkFaceThermalSeries
from packages.schemas.window_eval import HourState, ScheduledBar, SeriesPoint, Verdict

from scripts.make_ribbon_fixture import _bar, _horizon, _series_for_face
from scripts.make_thermal_fixtures import TZ

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO = _REPO_ROOT / "data" / "project_demo"
FIXTURES = _REPO_ROOT / "data" / "fixtures"
THERMAL_BUNDLE = FIXTURES / "sample_thermal_bundle.json"     # the Day-4.5 bundle T1's ribbon uses

LOOKAHEAD_H = 72
ANCHOR = datetime(2026, 8, 24, 0, 0, tzinfo=TZ)             # demo window start
HORIZON_END = ANCHOR + timedelta(hours=LOOKAHEAD_H)
SITE_ID = "NPX-FAB-P2"
RUN_ID = "agent-2026-08-24-0000-commit-live"
# The deterministic proposer's name, used when LLM_BASE_URL is unset. When a model
# IS configured, run_agent reports get_model() instead. The gate is ALWAYS pure
# Python; the model only chooses a strategy, never a number (§7, §8.2).
MODEL_NAME = "none (deterministic proposer — fixed strategy order, no LLM)"

# Verdicts that count as "at risk / flagged" (§8.1 / the sample fixture's
# definition). NO_DATA is a fail-closed data gap, not a risk flag — it is counted
# and surfaced separately, never folded into flagged_count.
_FLAGGED = {Verdict.AT_RISK, Verdict.NON_COMPLIANT, Verdict.INSUFFICIENT_WINDOW}


def _now(offset_s: float = 0.0) -> datetime:
    return ANCHOR + timedelta(seconds=offset_s)


# --------------------------------------------------------------------------- #
# Tools the agent calls (read-only; the 13-tool surface lands Day 7-8)
# --------------------------------------------------------------------------- #

def _load_activities() -> list[dict]:
    return json.loads((DEMO / "activities.json").read_text(encoding="utf-8"))["activities"]


def _load_faces() -> dict[str, dict]:
    gj = json.loads((DEMO / "work_faces.geojson").read_text(encoding="utf-8"))
    return {f["properties"]["id"]: f["properties"] for f in gj["features"]}


def _load_thermal() -> dict[str, WorkFaceThermalSeries]:
    bundle = ThermalSeriesBundle.model_validate_json(THERMAL_BUNDLE.read_text(encoding="utf-8"))
    return {s.work_face_id: s for s in bundle.series}


def _load_precedences() -> list[dict]:
    return json.loads((DEMO / "activities.json").read_text(encoding="utf-8"))["precedences"]


def _successor_map(preds: list[dict]) -> dict[str, list[str]]:
    """activity_id -> the ids that depend on it (its FS successors)."""
    out: dict[str, list[str]] = {}
    for link in preds:
        out.setdefault(link["pred_id"], []).append(link["activity_id"])
    return out


def list_activities_in_lookahead(lookahead_h: int = LOOKAHEAD_H) -> list[dict]:
    """Activities whose planned window intersects [ANCHOR, ANCHOR+lookahead_h]."""
    end = ANCHOR + timedelta(hours=lookahead_h)
    out = []
    for a in _load_activities():
        s = datetime.fromisoformat(a["planned_start"])
        f = datetime.fromisoformat(a["planned_finish"])
        if s < end and f > ANCHOR:
            out.append(a)
    return out


def get_work_face_thermal(work_face_id: str, thermal: dict[str, WorkFaceThermalSeries]
                          ) -> WorkFaceThermalSeries | None:
    return thermal.get(work_face_id)


# --------------------------------------------------------------------------- #
# Conflict detection
# --------------------------------------------------------------------------- #

def _horizon_days() -> list[str]:
    n = LOOKAHEAD_H // 24
    return [(ANCHOR + timedelta(days=i)).date().isoformat() for i in range(n)]


def _day_bounds(day: str) -> tuple[datetime, datetime]:
    d = datetime.fromisoformat(day + "T00:00:00").replace(tzinfo=TZ)
    return d, d + timedelta(days=1)


def _bar_overlaps_day(bar: ScheduledBar, day: str) -> bool:
    d0, d1 = _day_bounds(day)
    return bar.start < d1 and bar.finish > d0


def _open_clock_hours_on_day(ev, day: str) -> float:
    """Open clock-hours on a face's evaluation within one calendar day."""
    total = 0.0
    step_h = 1.0
    ts = [c.ts for c in ev.hours]
    if len(ts) >= 2:
        step_h = (ts[1] - ts[0]).total_seconds() / 3600.0
    for c in ev.hours:
        if c.ts.date().isoformat() == day and c.state is HourState.OPEN:
            total += step_h
    return round(total, 2)


def _demanded_productive_hours_on_day(ev, bar: ScheduledBar, day: str) -> float:
    """Productive crew-hours this activity commits ON THAT SHIFT (bar clipped to
    the day), after the WBGT haircut — via constraints.productive_hours. Clipping
    to the day keeps a multi-day activity from over-demanding a single shift."""
    d0, d1 = _day_bounds(day)
    interval = C.Interval(max(bar.start, d0), min(bar.finish, d1))
    if interval.end <= interval.start:
        return 0.0
    return C.productive_hours(interval, ev.hours)


# --------------------------------------------------------------------------- #
# The loop
# --------------------------------------------------------------------------- #

def run_agent(lookahead_h: int = LOOKAHEAD_H, *, use_llm: bool = True) -> AgentRun:
    reg = load_registry()
    faces = _load_faces()
    thermal = _load_thermal()
    acts_by_id = {a["id"]: a for a in _load_activities()}
    succ_map = _successor_map(_load_precedences())

    steps: list[AgentStep] = []
    seq = 0

    # --- SCAN --------------------------------------------------------------
    in_window = list_activities_in_lookahead(lookahead_h)
    thermal_sensitive = [a for a in in_window if a["thermal_sensitive"] and a["trade_id"]]
    steps.append(AgentStep(
        seq=seq, type=StepType.SCAN, at=_now(0),
        title=f"Scanned {len(in_window)} activities in the {lookahead_h} h lookahead",
        detail=f"Listed every activity whose planned window intersects the {lookahead_h} h "
               f"horizon from {ANCHOR:%Y-%m-%d %H:%M} for site {SITE_ID}. "
               f"{len(thermal_sensitive)} are thermal-sensitive with a trade.",
        tool_calls=[ToolCall(
            tool=ToolName.LIST_ACTIVITIES_IN_LOOKAHEAD, args={"lookahead_h": lookahead_h},
            ok=True, result_summary=f"{len(in_window)} in horizon, {len(thermal_sensitive)} thermal-sensitive")],
    ))
    seq += 1

    # --- EVALUATE ----------------------------------------------------------
    evals: dict[str, object] = {}
    bars: dict[str, ScheduledBar] = {}
    tool_calls: list[ToolCall] = []
    skipped: list[str] = []
    seen_faces: set[str] = set()
    for a in thermal_sensitive:
        wf = a["work_face_id"]
        series_obj = get_work_face_thermal(wf, thermal)
        if series_obj is None or wf not in faces:
            skipped.append(a["id"])
            continue
        if wf not in seen_faces:
            tool_calls.append(ToolCall(
                tool=ToolName.GET_WORK_FACE_THERMAL, args={"work_face_id": wf}, ok=True,
                result_summary=f"{len(series_obj.points)} h series, confidence {series_obj.confidence.value}",
                fg_activity_ids=list(series_obj.fg_activity_ids)))
            seen_faces.add(wf)
        series, ts = _series_for_face(series_obj, faces[wf]["surface_class"])
        bar = _bar(a)
        ev = evaluate_window(
            trade_id=a["trade_id"], series=series, ts=ts, scheduled=bar,
            activity_id=a["id"], activity_name=a["name"], wbs=a.get("wbs"),
            work_face_id=wf, work_face_name=faces[wf]["name"],
            run_id=RUN_ID, horizon=_horizon(), registry=reg)
        evals[a["id"]] = ev
        bars[a["id"]] = bar
        tool_calls.append(ToolCall(
            tool=ToolName.EVALUATE_WINDOW, args={"activity_id": a["id"]}, ok=True,
            result_summary=f"verdict {ev.verdict.value}"
                           + (f"; binding {ev.binding_constraint.constraint_id}" if ev.binding_constraint else "")))

    flagged = [aid for aid, ev in evals.items() if ev.verdict in _FLAGGED]
    no_data = [aid for aid, ev in evals.items() if ev.verdict is Verdict.NO_DATA]
    detail = (f"Ran the deterministic window engine (thermal twin -> evaluate_window) on each. "
              f"{len(flagged)} are at_risk / non_compliant / insufficient_window.")
    if no_data:
        detail += (f" {len(no_data)} returned no_data (fail-closed — mostly continuity runs that "
                   f"extend past the {LOOKAHEAD_H} h horizon); counted separately, not as flagged.")
    if skipped:
        detail += f" {len(skipped)} skipped (no thermal series for the face)."
    steps.append(AgentStep(
        seq=seq, type=StepType.EVALUATE, at=_now(3),
        title=f"Flagged {len(flagged)} of {len(evals)} evaluated as at-risk",
        detail=detail, activity_ids=flagged, tool_calls=tool_calls,
    ))
    seq += 1

    # --- CONFLICT ----------------------------------------------------------
    # Group by (work face, shift day); an activity appears on every horizon day
    # its bar overlaps. A conflict is a shift where the productive hours demanded
    # exceed the open hours available.
    groups: dict[tuple[str, str], list[str]] = {}
    for aid, ev in evals.items():
        for day in _horizon_days():
            if _bar_overlaps_day(bars[aid], day):
                groups.setdefault((ev.work_face_id, day), []).append(aid)

    conflicts: list[Conflict] = []
    cn = 0
    for (wf, day), aids in sorted(groups.items()):
        if len(aids) < 2:
            continue
        compliant = _open_clock_hours_on_day(evals[aids[0]], day)
        demanded = round(sum(_demanded_productive_hours_on_day(evals[aid], bars[aid], day)
                             for aid in aids), 2)
        if demanded <= compliant:
            continue
        cn += 1
        conflicts.append(Conflict(
            id=f"C{cn}", work_face_id=wf, shift_date=day,
            competing_activity_ids=sorted(aids),
            compliant_hours=compliant, demanded_hours=demanded,
            description=(f"{len(aids)} activities on {wf} compete for the {day} shift: "
                         f"{demanded:g} productive hours demanded against {compliant:g} open hours."),
        ))

    steps.append(AgentStep(
        seq=seq, type=StepType.CONFLICT, at=_now(5),
        title=f"{len(conflicts)} conflict(s) across {len({c.work_face_id for c in conflicts})} work face(s)",
        detail="Grouped the evaluated activities by work face and shift; emitted a conflict "
               "wherever the productive hours demanded exceed the open hours available.",
        activity_ids=sorted({aid for c in conflicts for aid in c.competing_activity_ids}),
    ))
    seq += 1

    # --- PROPOSE + GATE + ACT/ESCALATE (Day 7, Task D) --------------------------
    # The LLM (when configured) picks WHICH strategy to attempt first; the packer
    # does the arithmetic and the pure-Python gate disposes. split → shift →
    # mitigate → rfi → escalate. A deterministic proposer runs when no model is set,
    # which keeps CI green (hard rule 4).
    systems = MockSiteSystems()
    crew = YamlCrewSource()
    cfg = load_policy()
    model_configured = use_llm and is_configured()

    targets = _resolution_targets(evals, acts_by_id, conflicts)
    conflict_of = {aid: c for c in conflicts for aid in c.competing_activity_ids}
    resolved = 0
    escalated = 0

    for aid in targets:
        ev = evals[aid]
        act = acts_by_id[aid]
        successors = [acts_by_id[s] for s in succ_map.get(aid, []) if s in acts_by_id]
        order = strategy_order_for(ev, act, use_llm=model_configured)
        attempts = resolve_activity(
            ev, act, successors=successors, anchor=ANCHOR,
            systems=systems, crew=crew, cfg=cfg, strategy_order=order,
        )
        cid = conflict_of[aid].id if aid in conflict_of else None
        seq = _emit_attempts(steps, seq, ev, attempts, cid)
        outcome = attempts[-1]
        if outcome.kind is ProposalKind.ESCALATE or outcome.escalated:
            escalated += 1
            if aid in conflict_of:
                conflict_of[aid].resolved_by_step_seq = seq - 1
        elif outcome.resolved:
            resolved += 1
            if aid in conflict_of:
                conflict_of[aid].resolved_by_step_seq = seq - 1

    model_name = get_model() if model_configured else MODEL_NAME

    return AgentRun(
        run_id=RUN_ID, site_id=SITE_ID, started_at=_now(0), finished_at=_now(6 + len(targets)),
        status=RunStatus.COMPLETED, model_name=model_name, lookahead_h=lookahead_h, tier="commit",
        scanned_count=len(in_window), flagged_count=len(flagged),
        conflicts_count=len(conflicts), resolved_count=resolved, escalated_count=escalated,
        conflicts=conflicts, steps=steps, replay=not model_configured,
    )


# --------------------------------------------------------------------------- #
# Target selection + step emission for the PROPOSE/GATE/ACT stage
# --------------------------------------------------------------------------- #

def _resolution_targets(evals: dict, acts_by_id: dict, conflicts: list[Conflict],
                        cap: int = 12) -> list[str]:
    """The flagged activities worth a decision: near-critical or hold-point ones
    (the demo beats), plus every conflict participant. Tightest float first, so
    the agent spends its reasoning where the schedule is most fragile."""
    picked: list[str] = []
    seen: set[str] = set()
    for aid, ev in evals.items():
        if ev.verdict not in _FLAGGED:
            continue
        a = acts_by_id.get(aid, {})
        if a.get("is_near_critical") or a.get("hold_point"):
            picked.append(aid)
            seen.add(aid)
    for c in conflicts:
        for aid in c.competing_activity_ids:
            if aid not in seen and aid in evals:
                picked.append(aid)
                seen.add(aid)
    picked.sort(key=lambda x: (not acts_by_id[x].get("is_near_critical"),
                               acts_by_id[x].get("total_float_d") if acts_by_id[x].get("total_float_d") is not None else 1e9))
    return picked[:cap]


def _emit_attempts(steps: list[AgentStep], seq: int, ev, attempts: list[Attempt],
                   conflict_id: str | None) -> int:
    """Turn one activity's ladder into trace steps: a PROPOSE (and, for a gated
    rung, a GATE) per attempt, then the ACT or ESCALATE outcome step."""
    for att in attempts:
        gated = att.gated
        tool_calls = []
        if att.kind in (ProposalKind.SPLIT, ProposalKind.SHIFT):
            tool_calls = [ToolCall(tool=ToolName.PROPOSE_RESEQUENCE,
                                   args={"activity_id": ev.activity_id, "kind": att.kind.value},
                                   ok=True, result_summary=att.summary)]
        steps.append(AgentStep(
            seq=seq, type=StepType.PROPOSE, at=_now(6 + seq),
            title=f"Propose {att.kind.value} for {ev.activity_id}",
            detail=att.proposal.rationale, activity_ids=[ev.activity_id],
            conflict_id=conflict_id, tool_calls=tool_calls, proposal=att.proposal,
        ))
        seq += 1
        if gated and att.verdict is not None:
            steps.append(AgentStep(
                seq=seq, type=StepType.GATE, at=_now(6 + seq),
                title=f"Gate: {att.verdict.decision.value} ({att.verdict.rule_id})",
                detail=att.verdict.reason, activity_ids=[ev.activity_id],
                conflict_id=conflict_id, gate=att.verdict,
            ))
            seq += 1

    outcome = attempts[-1]
    if outcome.kind is ProposalKind.ESCALATE or outcome.escalated:
        steps.append(AgentStep(
            seq=seq, type=StepType.ESCALATE, at=_now(6 + seq),
            title=f"Escalate {ev.activity_id} to the superintendent",
            detail=outcome.proposal.rationale if outcome.kind is ProposalKind.ESCALATE
                   else f"{outcome.kind.value} denied — {outcome.verdict.reason if outcome.verdict else ''}",
            activity_ids=[ev.activity_id], conflict_id=conflict_id,
            tool_calls=[ToolCall(tool=ToolName.ESCALATE_TO_SUPERINTENDENT,
                                 args={"activity_id": ev.activity_id}, ok=True,
                                 result_summary="routed to a human with the tradeoff")],
        ))
        seq += 1
    elif outcome.resolved:
        steps.append(AgentStep(
            seq=seq, type=StepType.ACT, at=_now(6 + seq),
            title=f"Act: {outcome.tool.value} on {ev.activity_id}",
            detail=f"{outcome.summary}"
                   + (f" — gate approved ({outcome.verdict.rule_id})" if outcome.verdict else ""),
            activity_ids=[ev.activity_id], conflict_id=conflict_id,
            tool_calls=[ToolCall(tool=outcome.tool, args={"activity_id": ev.activity_id},
                                 ok=True, gated=outcome.gated, result_summary=outcome.summary)],
        ))
        seq += 1
    return seq


__all__ = ["run_agent", "list_activities_in_lookahead", "get_work_face_thermal",
           "LOOKAHEAD_H", "ANCHOR"]
