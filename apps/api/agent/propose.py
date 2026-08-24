"""
WORKFACE — PROPOSE: the strategy ladder + the gate-context builder.  T3, Day 7, Task D.

    from apps.api.agent.propose import resolve_activity, STRATEGY_ORDER

This is where the agent decides WHAT to try for a flagged activity, and in what
order — the one place the LLM has a job (§8.2). The order is fixed by the brief:

    SPLIT  →  SHIFT  →  MITIGATE  →  RFI  →  ESCALATE                     (§7, Task D)

because the demo beat is that the agent finds a split *instead of* an expensive
shift, which only happens if split is tried first. The LLM may reorder the ladder
and writes the rationale a human reads; it NEVER computes a date — every number
comes from the deterministic packer (pack.py) and the deterministic gate
(policy.py). A deterministic fallback (no LLM) uses the fixed order and templated
rationales, which is what keeps CI green (hard rule 4) and is the demo insurance.

Each rung produces a Proposal + a GateContext; gated rungs (shift, split) are run
through `evaluate_policy` and only an APPROVE resolves. A hard-stop denial
(hold point, milestone, precedence, stale data) escalates immediately rather than
trying to mitigate around a wall that cannot be moved.

# ---------------------------------------------------------------------------
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task
#   fg_activity_id  = a FortyGuard async job handle
# ---------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from apps.api.agent.policy import (
    GateContext,
    MilestoneRisk,
    PolicyConfig,
    evaluate_policy,
    fail_closed_on_stale_forecast,
    load_policy,
    no_move_inspection_hold_point,
)
from apps.api.sequencer.pack import (
    BlockingConstraint,
    PackActivity,
    PlaceStatus,
    YamlCrewSource,
    activity_from_eval,
    pack,
)
from packages.schemas.agent_trace import (
    GateDecision,
    GateVerdict,
    Proposal,
    ProposalKind,
    ToolName,
)
from packages.schemas.window_eval import HourState, Verdict, WindowEval

STRATEGY_ORDER = (
    ProposalKind.SPLIT,
    ProposalKind.SHIFT,
    ProposalKind.MITIGATE,
    ProposalKind.RFI,
    ProposalKind.ESCALATE,
)

# Gate denials that no mitigation can route around — escalate straight away.
_HARD_STOP_RULES = {
    "no_move_inspection_hold_point",
    "no_move_past_milestone",
    "no_precedence_violation",
    "fail_closed_on_stale_forecast",
}

_KIND_TOOL = {
    ProposalKind.SPLIT: ToolName.SPLIT_ACTIVITY,        # gated
    ProposalKind.SHIFT: ToolName.SHIFT_ACTIVITY,        # gated
    ProposalKind.MITIGATE: ToolName.REQUEST_MITIGATION,
    ProposalKind.RFI: ToolName.RAISE_RFI,
    ProposalKind.ESCALATE: ToolName.ESCALATE_TO_SUPERINTENDENT,
}
_GATED_KINDS = {ProposalKind.SPLIT, ProposalKind.SHIFT}


@dataclass
class Attempt:
    """One rung of the ladder, and what the gate said about it."""
    kind: ProposalKind
    tool: ToolName
    proposal: Proposal
    context: GateContext
    verdict: GateVerdict | None          # None for non-gated tools
    gated: bool
    resolved: bool
    escalated: bool
    summary: str


# --------------------------------------------------------------------------- #
# Float + milestone + heat models (deterministic; explainable on a slide)
# --------------------------------------------------------------------------- #

def _iso(s: str) -> datetime:
    return datetime.fromisoformat(s)


def float_consumed_d(act: dict, placed_start: datetime) -> float:
    """Working-time float consumed = fraction of the CPM slack window
    [early_start, late_start] used by this placement, scaled to the generator's
    reported total_float_d. Placing at/after late_start consumes >= 100%. Kept
    consistent with the data's own float so the gate's fractional cap is meaningful."""
    es, ls = _iso(act["early_start"]), _iso(act["late_start"])
    tf = float(act.get("total_float_d") or 0.0)
    span = (ls - es).total_seconds()
    if span <= 0:
        return 0.0
    frac = (placed_start - es).total_seconds() / span
    return round(max(0.0, frac) * tf, 3)


def _milestone_risks(act: dict, placed_finish: datetime, successors: list[dict]) -> list[MilestoneRisk]:
    """Project each milestone-carrying successor by the slip this placement causes."""
    slip = placed_finish - _iso(act["early_finish"])
    risks: list[MilestoneRisk] = []
    for s in successors:
        if s.get("milestone_date"):
            risks.append(MilestoneRisk(
                activity_id=s["id"],
                milestone_name=s.get("milestone_name") or "milestone",
                milestone_date=_iso(s["milestone_date"]),
                projected_date=_iso(s["early_finish"]) + slip,
            ))
    return risks


def _min_work_fraction(ev: WindowEval, start: datetime, finish: datetime) -> float | None:
    fracs = [c.productive_fraction for c in ev.hours if start <= c.ts < finish]
    return round(min(fracs), 3) if fracs else None


# --------------------------------------------------------------------------- #
# Rungs
# --------------------------------------------------------------------------- #

def _pack_whole(ev: WindowEval, act: dict, anchor: datetime, crew) -> "object":
    pa = activity_from_eval(ev, crew_size=int(act.get("crew_size") or 1),
                            total_float_d=float(act.get("total_float_d") or 0.0))
    return pack([pa], crew=crew, anchor=anchor).placements[ev.activity_id]


def _split_feasible(ev: WindowEval, act: dict, anchor: datetime, crew):
    """A split is worth proposing only when NO single interval holds the whole
    activity but two SEPARATE intervals each hold half — 'two dawn-free windows'.
    Returns (placement_a, placement_b) or None."""
    need = ev.scheduled.duration_h
    ivs = sorted(ev.open_intervals, key=lambda x: x.start)
    if any(iv.productive_h + 1e-9 >= need for iv in ivs):
        return None                                     # whole fits one window; a split is not the move
    half = need / 2.0
    usable = [iv for iv in ivs if iv.productive_h + 1e-9 >= half]
    if len(usable) < 2:
        return None
    crew_size = int(act.get("crew_size") or 1)
    tf = float(act.get("total_float_d") or 0.0)
    a1 = PackActivity(ev.activity_id + "#1", ev.trade_id, ev.work_face_id, half, crew_size, tf,
                      ev.scheduled.start, [usable[0]])
    a2 = PackActivity(ev.activity_id + "#2", ev.trade_id, ev.work_face_id, half, crew_size, tf,
                      ev.scheduled.start, [usable[1]])
    r = pack([a1, a2], crew=crew, anchor=anchor)
    pa, pb = r.placements[a1.id], r.placements[a2.id]
    if pa.status is not PlaceStatus.UNPLACEABLE and pb.status is not PlaceStatus.UNPLACEABLE:
        return pa, pb
    return None


def _preferred_mitigations(ev: WindowEval, blocker: BlockingConstraint | None) -> list[str]:
    """Order the catalog by what actually addresses this activity's problem, so the
    agent does not offer shade for a night-only window. Blocker-first, then the
    binding constraint's family."""
    if blocker is BlockingConstraint.CREW_UNAVAILABLE:
        return ["night_shift", "crew_augment"]          # night-only window or short crew
    bc = (ev.binding_constraint.constraint_id if ev.binding_constraint else "") or ""
    if "offset" in bc or "dew" in bc:
        return ["preheat_substrate", "shade_temporary", "night_shift"]
    if "continuity" in bc or "cure" in bc:
        return ["heated_enclosure", "preheat_substrate", "night_shift"]
    if "human" in bc or "wbgt" in bc:
        return ["evaporative_cooling", "shade_temporary", "night_shift"]
    if "composite" in bc or "evapor" in bc:
        return ["readymix_retimed", "split_pour", "shade_temporary"]
    if "band" in bc:
        return ["shade_temporary", "night_shift", "preheat_substrate"]
    return []


def _pick_mitigation(ev: WindowEval, act: dict, systems, when: datetime,
                     *, blocker: BlockingConstraint | None = None) -> dict | None:
    """The best available catalog mitigation: one that ADDRESSES the binding
    constraint / blocker first, then any applicable one, checked through T2's
    MockSiteSystems (already merged, §5)."""
    if systems is None:
        return None
    from apps.api.sitefeeds.sitesystems import load_catalog
    catalog = load_catalog()["mitigations"]
    by_id = {m["id"]: m for m in catalog}
    preferred = [by_id[i] for i in _preferred_mitigations(ev, blocker) if i in by_id]
    ordered = preferred + [m for m in catalog if m not in preferred]

    for mit in ordered:
        applies = mit.get("applies_to_trades") or []
        if "*" not in applies and ev.trade_id not in applies:
            continue
        res = systems.can_request_mitigation(
            mit["id"], when=when, trade_id=ev.trade_id, work_face_id=ev.work_face_id,
            headcount=int(act.get("crew_size") or 5),
            area_m2=act.get("quantity") if act.get("quantity_unit") in ("m2", "sqm") else None,
        )
        if res["ok"]:
            return res
    return None


# --------------------------------------------------------------------------- #
# The ladder
# --------------------------------------------------------------------------- #

def resolve_activity(
    ev: WindowEval,
    act: dict,
    *,
    successors: list[dict],
    anchor: datetime,
    systems=None,
    crew=None,
    cfg: PolicyConfig | None = None,
    strategy_order: tuple[ProposalKind, ...] = STRATEGY_ORDER,
    forecast_age_h: float = 0.5,
) -> list[Attempt]:
    """Run the ladder for one flagged activity. Returns every rung tried, in
    order; the last Attempt is the outcome (resolved or escalated)."""
    cfg = cfg or load_policy()
    crew = crew or YamlCrewSource()
    attempts: list[Attempt] = []
    aid = ev.activity_id
    last_blocker: BlockingConstraint | None = None

    # -- Pre-check the INHERENT hard stops (§9). A hold point or a stale forecast
    # forbids the agent from moving this activity AT ALL — checked here so a
    # hold-point activity can never slip past the gate into a mitigation just
    # because the packer happened to find no placement to gate.
    precheck = GateContext(
        kind=ProposalKind.SHIFT, activity_ids=[aid],
        hold_point=act.get("hold_point"), forecast_age_h=forecast_age_h,
        is_near_critical=bool(act.get("is_near_critical")),
    )
    for rule in (fail_closed_on_stale_forecast, no_move_inspection_hold_point):
        v = rule(precheck, cfg)
        if v is not None:
            prop = Proposal(kind=ProposalKind.SHIFT, activity_ids=[aid],
                            rationale=f"Attempt to resequence {aid} — blocked before any placement.")
            _record(attempts, ProposalKind.SHIFT, prop, precheck, v, f"blocked: {v.rule_id}")
            return _finish_escalate(attempts, ev, act, cfg, forecast_age_h)

    def base_ctx(kind: ProposalKind, *, start=None, finish=None) -> GateContext:
        risks = _milestone_risks(act, finish, successors) if finish else []
        return GateContext(
            kind=kind, activity_ids=[aid],
            is_near_critical=bool(act.get("is_near_critical")),
            float_days_consumed=float_consumed_d(act, start) if start else 0.0,
            activity_total_float_d=float(act.get("total_float_d") or 0.0),
            milestones=risks,
            hold_point=act.get("hold_point"),
            out_of_spec=(ev.verdict is Verdict.NON_COMPLIANT),
            out_of_spec_detail=(ev.binding_constraint.label if ev.binding_constraint else ""),
            placement_start=start,
            wbgt_work_fraction=_min_work_fraction(ev, start, finish) if (start and finish) else None,
            forecast_age_h=forecast_age_h,
        )

    for kind in strategy_order:
        # -- SPLIT (gated) --------------------------------------------------
        if kind is ProposalKind.SPLIT:
            split = _split_feasible(ev, act, anchor, crew)
            if split is None:
                continue
            pa, pb = split
            finish = max(pa.finish, pb.finish)
            ctx = base_ctx(ProposalKind.SPLIT, start=pa.start, finish=finish)
            prop = Proposal(
                kind=ProposalKind.SPLIT, activity_ids=[aid],
                rationale=(f"Split {aid} across two dawn-free windows "
                           f"({pa.start:%d %b %H:%M} and {pb.start:%d %b %H:%M}) so each half sits inside a "
                           f"compliant interval — the cheapest fix, tried before any shift."),
                float_days_consumed=max(pa.float_days_consumed, pb.float_days_consumed),
            )
            v = evaluate_policy(prop, ctx, cfg)
            att = _record(attempts, ProposalKind.SPLIT, prop, ctx, v,
                          f"split into {pa.start:%d %b %H:%M} + {pb.start:%d %b %H:%M}")
            if att.resolved:
                return attempts
            if v.rule_id in _HARD_STOP_RULES:
                return _finish_escalate(attempts, ev, act, cfg, forecast_age_h)
            continue

        # -- SHIFT (gated) --------------------------------------------------
        if kind is ProposalKind.SHIFT:
            pl = _pack_whole(ev, act, anchor, crew)
            if pl.status is PlaceStatus.UNPLACEABLE:
                last_blocker = pl.blocked_by            # informs which mitigation to prefer
                continue                                # nothing to shift into; let mitigate/escalate handle it
            ctx = base_ctx(ProposalKind.SHIFT, start=pl.start, finish=pl.finish)
            prop = Proposal(
                kind=ProposalKind.SHIFT, activity_ids=[aid],
                rationale=(f"Shift {aid} to its earliest compliant window "
                           f"({pl.start:%d %b %H:%M}), consuming {ctx.float_days_consumed:g} d of its "
                           f"{ctx.activity_total_float_d:g} d float."),
                float_days_consumed=ctx.float_days_consumed,
                solver_payload={"start": pl.start.isoformat(), "finish": pl.finish.isoformat()},
            )
            v = evaluate_policy(prop, ctx, cfg)
            att = _record(attempts, ProposalKind.SHIFT, prop, ctx, v,
                          f"shift to {pl.start:%d %b %H:%M} ({ctx.float_days_consumed:g} d float)")
            if att.resolved:
                return attempts
            if v.rule_id in _HARD_STOP_RULES:
                return _finish_escalate(attempts, ev, act, cfg, forecast_age_h)
            continue

        # -- MITIGATE (not gated) ------------------------------------------
        if kind is ProposalKind.MITIGATE:
            mit = _pick_mitigation(ev, act, systems, ev.scheduled.start, blocker=last_blocker)
            if mit is None:
                continue
            m = mit["mitigation"]
            prop = Proposal(
                kind=ProposalKind.MITIGATE, activity_ids=[aid],
                rationale=(f"Request '{m['name']}' (lead {m['lead_time_h']} h, "
                           f"${m['cost_usd_per_day']}/day) — available per the site systems, and it "
                           f"addresses the binding {ev.binding_constraint.label if ev.binding_constraint else 'constraint'}."),
            )
            ctx = base_ctx(ProposalKind.MITIGATE)
            _record(attempts, ProposalKind.MITIGATE, prop, ctx, None,
                    f"request {m['id']} ({m['name']})")
            return attempts

        # -- RFI (not gated; the ONLY path to accept out-of-spec) -----------
        if kind is ProposalKind.RFI:
            if ev.verdict is not Verdict.NON_COMPLIANT:
                continue
            prop = Proposal(
                kind=ProposalKind.RFI, activity_ids=[aid],
                rationale=(f"No compliant window and no mitigation clears the binding "
                           f"{ev.binding_constraint.label if ev.binding_constraint else 'constraint'}. "
                           f"Raise an RFI to the engineer of record — the only party who may accept "
                           f"out-of-spec application."),
            )
            ctx = base_ctx(ProposalKind.RFI)
            _record(attempts, ProposalKind.RFI, prop, ctx, None, "raise RFI to the EOR")
            return attempts

        # -- ESCALATE (not gated) ------------------------------------------
        if kind is ProposalKind.ESCALATE:
            return _finish_escalate(attempts, ev, act, cfg, forecast_age_h)

    return _finish_escalate(attempts, ev, act, cfg, forecast_age_h)


def _record(attempts: list[Attempt], kind: ProposalKind, prop: Proposal,
            ctx: GateContext, v: GateVerdict | None, summary: str) -> Attempt:
    gated = kind in _GATED_KINDS
    resolved = (not gated) or (v is not None and v.decision is GateDecision.APPROVE)
    escalated = bool(v and v.escalated)
    att = Attempt(kind, _KIND_TOOL[kind], prop, ctx, v, gated, resolved, escalated, summary)
    attempts.append(att)
    return att


def _finish_escalate(attempts: list[Attempt], ev: WindowEval, act: dict,
                     cfg: PolicyConfig, forecast_age_h: float) -> list[Attempt]:
    """The escalation note states what was tried, what each attempt would cost,
    and why none was acceptable (§9) — not 'escalating for review'."""
    tried = "; ".join(
        f"{a.kind.value} → {a.verdict.reason}" if a.verdict else f"{a.kind.value} → {a.summary}"
        for a in attempts
    ) or "no automatic resolution was feasible"
    rationale = (
        f"Escalating {ev.activity_id} ({ev.activity_name}) to the superintendent. "
        f"Binding constraint: {ev.binding_constraint.label if ev.binding_constraint else ev.verdict.value}. "
        f"Tried: {tried}. No option is acceptable without a human tradeoff — the decision to "
        f"spend contractual float, move a hold point or a milestone, or run out-of-spec work is not the agent's."
    )
    prop = Proposal(kind=ProposalKind.ESCALATE, activity_ids=[ev.activity_id], rationale=rationale[:1200])
    ctx = GateContext(kind=ProposalKind.ESCALATE, activity_ids=[ev.activity_id],
                      is_near_critical=bool(act.get("is_near_critical")),
                      hold_point=act.get("hold_point"), forecast_age_h=forecast_age_h)
    att = Attempt(ProposalKind.ESCALATE, ToolName.ESCALATE_TO_SUPERINTENDENT, prop, ctx, None,
                  gated=False, resolved=False, escalated=True, summary="escalate to superintendent")
    attempts.append(att)
    return attempts


# --------------------------------------------------------------------------- #
# The one LLM job (§8.2): choose which strategy to attempt first. The model never
# computes a date — it picks a strategy name; the packer and the gate do the rest.
# Designed to never need `tool_choice` (docs/LLM_SETUP.md §3 portability).
# --------------------------------------------------------------------------- #

_STRATEGY_TOOLS = [
    {"type": "function", "function": {
        "name": k.value,
        "description": {
            "split": "Split the activity across two compliant windows. Try this FIRST — it is the cheapest fix.",
            "shift": "Move the whole activity to its earliest compliant window, spending float.",
            "mitigate": "Request a site mitigation (shade, night lighting, preheat, extra crew, retimed ready-mix).",
            "rfi": "Raise an RFI to the engineer of record — the only way to accept out-of-spec work.",
            "escalate": "Escalate to the superintendent when no option is acceptable without a human tradeoff.",
        }[k.value],
        "parameters": {"type": "object", "properties": {
            "reason": {"type": "string", "description": "One sentence: why this strategy, for this activity."}
        }},
    }}
    for k in (ProposalKind.SPLIT, ProposalKind.SHIFT, ProposalKind.MITIGATE, ProposalKind.RFI, ProposalKind.ESCALATE)
]

_SYSTEM_PROMPT = (
    "You are the resolution planner for a construction thermal-window agent. You do NOT do arithmetic, "
    "compute dates, or evaluate physics — a deterministic solver and policy gate do that. Your ONLY job is "
    "to choose which resolution strategy to ATTEMPT FIRST for a flagged activity, by calling exactly one of "
    "the provided tools. Prefer a split over a shift; prefer any schedule fix over an RFI; escalate only when "
    "the activity carries an inspection hold point or a contractual milestone that a move would breach."
)


def llm_choose_strategy(summary: str, *, retries: int = 3) -> ProposalKind | None:
    """Ask the configured model to pick a first strategy. Returns None if the LLM
    is not configured or the reply names no known tool (caller falls back to the
    fixed order). Never raises into the loop.

    Retries with backoff on ANY transport error — provider-agnostic (no exception-
    class branching, keeping §10's one-client rule). A hosted dev endpoint (Gemini,
    Groq) rate-limits a burst of per-activity calls; without the retry those 429s
    read as 'the model chose nothing', masking that the choice itself was fine."""
    import time

    from apps.api.agent.llm import chat, is_configured
    if not is_configured():
        return None
    known = {k.value for k in ProposalKind}
    for attempt in range(retries):
        try:
            resp = chat(
                messages=[{"role": "system", "content": _SYSTEM_PROMPT},
                          {"role": "user", "content": summary}],
                tools=_STRATEGY_TOOLS, temperature=0,
            )
            choice = resp.choices[0].message
            name = None
            if getattr(choice, "tool_calls", None):
                name = choice.tool_calls[0].function.name
            elif choice.content:                        # some models answer in prose — scan for a strategy word
                low = choice.content.lower()
                name = next((k.value for k in ProposalKind if k.value in low), None)
            return ProposalKind(name) if name in known else None
        except Exception:
            if attempt == retries - 1:
                return None
            time.sleep(2.0 * (attempt + 1))             # 2 s, 4 s backoff on rate limits / transient errors
    return None


def strategy_order_for(ev: WindowEval, act: dict, *, use_llm: bool = True) -> tuple[ProposalKind, ...]:
    """The strategy order to run. Default is the fixed ladder; when the LLM is
    configured it may move ONE strategy to the front. The relative order of the
    rest is preserved so 'split before shift' still holds unless the model
    deliberately leads with a later rung (e.g. escalate on a hold point)."""
    if not use_llm:
        return STRATEGY_ORDER
    summary = (
        f"Activity {ev.activity_id} ({ev.activity_name}), trade {ev.trade_id}, on {ev.work_face_id}. "
        f"Verdict: {ev.verdict.value}. Binding constraint: "
        f"{ev.binding_constraint.label if ev.binding_constraint else 'n/a'}. "
        f"Near-critical: {bool(act.get('is_near_critical'))}. Total float: {act.get('total_float_d')} d. "
        f"Hold point: {act.get('hold_point') or 'none'}. "
        f"Open compliant windows on the horizon: {len(ev.open_intervals)}. "
        f"Choose the first strategy to attempt."
    )
    chosen = llm_choose_strategy(summary)
    if chosen is None:
        return STRATEGY_ORDER
    return (chosen, *[k for k in STRATEGY_ORDER if k is not chosen])


__all__ = ["STRATEGY_ORDER", "Attempt", "resolve_activity", "float_consumed_d",
           "llm_choose_strategy", "strategy_order_for"]
