"""
WORKFACE — Day-5 hand-written agent-trace fixtures.  T3.

    python -m scripts.make_agent_fixtures            # writes data/fixtures/*.json
    python -m scripts.make_agent_fixtures --check    # write + validate, non-zero on failure

Why this exists
---------------
Day 5's climatology work is BLOCKED on T2's historical sweep (no HistoricalSweepBundle
fixture has landed). So we do the other, more urgent Day-5 item: the hand-written
agent-trace and gate-verdict fixtures T1 builds the Trace view (Day 6) and the escalation
UI (Day 7) against — before the live agent loop exists.

The numbers are invented; the field names and shapes are exactly the
`packages/schemas/agent_trace.py` contract, validated before write so a fixture can never
drift from the schema T1 renders.

The two demo beats these cover
    (a) a pour/coating collision on the FAB2 deck, resolved with a SPLIT.
    (b) the deny case: the cheapest fix (a shift) would eat four days of float on a
        near-critical activity, so the policy gate DENIES it and the agent ESCALATES
        to a human instead — with the tradeoff written out and the policy rule_id named.
        That deny beat is ten seconds of demo and it buys enormous credibility.

# ---------------------------------------------------------------------------
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task (from P6 / the generator)
#   fg_activity_id  = a FortyGuard async job handle (from submit -> /v1/status/{id})
# ---------------------------------------------------------------------------
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from packages.schemas.agent_trace import (
    AgentRun,
    AgentStep,
    Conflict,
    GateDecision,
    GateVerdict,
    Proposal,
    ProposalKind,
    RunStatus,
    StepType,
    ToolCall,
    ToolName,
)

TZ = timezone(timedelta(hours=-7))                 # America/Phoenix, no DST, ever.
RUN_START = datetime(2026, 8, 22, 4, 0, tzinfo=TZ)
RUN_ID = "agent-2026-08-22-0400-commit"
SITE_ID = "NPX-FAB-P2"
MODEL_NAME = "llama-3.3-70b-instruct-turbo"

# Policy rule ids (config/policy.yaml, T3's Day-6 gate). Named here so T1 can render
# the deny beat verbatim before the gate exists.
RULE_SPLIT_OK = "split_within_float_ok"
RULE_MAX_FLOAT = "max_float_days_consumed"


def _at(minutes: float) -> datetime:
    return RUN_START + timedelta(minutes=minutes)


# --------------------------------------------------------------------------- #
# The two conflicts
# --------------------------------------------------------------------------- #

CONFLICT_POUR_COAT = Conflict(
    id="C1",
    work_face_id="WF-FAB2-11",
    shift_date="2026-08-24",
    competing_activity_ids=["A-2003", "A-2009"],       # slab pour vs high-build coating
    compliant_hours=5.0,
    demanded_hours=12.0,
    description="Slab pour (A-2003, 8 h) and epoxy coating (A-2009, 6 h) both want the "
                "05:00-10:00 compliant band on the FAB2 L3 deck — 5 open hours, 12 demanded.",
    resolved_by_step_seq=6,
)

CONFLICT_COAT_WELD = Conflict(
    id="C2",
    work_face_id="WF-FAB2-11",
    shift_date="2026-08-25",
    competing_activity_ids=["A-2009", "A-2006"],       # coating slip would push near-critical weld
    compliant_hours=4.0,
    demanded_hours=6.0,
    description="Slipping the coating (A-2009) to the next clean window would push the "
                "near-critical deck weld (A-2006) and consume four days of its float.",
    resolved_by_step_seq=10,
)


# --------------------------------------------------------------------------- #
# The gate verdicts (also emitted standalone for the escalation UI)
# --------------------------------------------------------------------------- #

GATE_APPROVE_SPLIT = GateVerdict(
    decision=GateDecision.APPROVE,
    rule_id=RULE_SPLIT_OK,
    reason="Split keeps both activities inside their compliant windows and consumes 0.5 d "
           "of float, under the 3.0 d cap for a near-critical activity.",
    escalated=False,
)

GATE_MODIFY_SHIFT = GateVerdict(
    decision=GateDecision.MODIFY,
    rule_id=RULE_SPLIT_OK,
    reason="Shift approved with the solver's amended start: 06:10 rather than the proposed "
           "05:00, so the pour clears the deck first. 0.8 d float consumed.",
    escalated=False,
    modified_params={"new_start": "2026-08-24T06:10:00-07:00", "float_days_consumed": 0.8},
)

GATE_DENY_ESCALATE = GateVerdict(
    decision=GateDecision.DENY,
    rule_id=RULE_MAX_FLOAT,
    reason="Denied: the shift would spend 4.0 d of float on near-critical A-2006, over the "
           "3.0 d cap. No compliant sequence preserves the milestone — escalating to the "
           "superintendent with the tradeoff.",
    escalated=True,
)


# --------------------------------------------------------------------------- #
# The run
# --------------------------------------------------------------------------- #

def build_run() -> AgentRun:
    steps: list[AgentStep] = [
        AgentStep(
            seq=0, type=StepType.SCAN, at=_at(0),
            title="Scanned 328 activities in the 72 h lookahead",
            detail="Listed every activity whose planned window falls inside the rolling 72 h "
                    "horizon for site NPX-FAB-P2.",
            tool_calls=[ToolCall(
                tool=ToolName.LIST_ACTIVITIES_IN_LOOKAHEAD, args={"lookahead_h": 72},
                ok=True, result_summary="328 activities in horizon", latency_ms=140)],
        ),
        AgentStep(
            seq=1, type=StepType.EVALUATE, at=_at(3),
            title="Flagged 41 of 328 as at-risk",
            detail="Ran the deterministic window engine on each activity (thermal twin -> "
                    "evaluate_window). 41 are at_risk, non_compliant or insufficient_window.",
            tool_calls=[
                ToolCall(tool=ToolName.GET_WORK_FACE_THERMAL, args={"work_face_id": "WF-FAB2-11"},
                         ok=True, result_summary="48 h series, confidence high",
                         fg_activity_ids=["fg-heatmap-FAB2DECK-0001", "fg-envparams-FAB2DECK-0001"],
                         latency_ms=95),
                ToolCall(tool=ToolName.EVALUATE_WINDOW, args={"activity_id": "A-2009"},
                         ok=True, result_summary="verdict at_risk; binding offset_dew_point",
                         latency_ms=12),
            ],
            activity_ids=["A-2009", "A-2003", "A-2006"],
        ),
        AgentStep(
            seq=2, type=StepType.CONFLICT, at=_at(4),
            title="2 conflicts on the FAB2 L3 deck",
            detail="Grouped the flagged activities by work face and shift; two sets compete "
                    "for the same compliant hours on WF-FAB2-11.",
            activity_ids=["A-2003", "A-2009", "A-2006"],
        ),

        # --- Beat (a): the pour/coating collision, resolved with a SPLIT ---
        AgentStep(
            seq=3, type=StepType.PROPOSE, at=_at(6), conflict_id="C1",
            title="Propose: split the coating around the pour",
            detail="The pour cannot move (hold point: city inspector). Split the 6 h coating "
                    "into 2 h before the pour crew arrives and 4 h after the deck clears, both "
                    "inside the dew-point-compliant band.",
            activity_ids=["A-2003", "A-2009"],
            tool_calls=[ToolCall(
                tool=ToolName.PROPOSE_RESEQUENCE, args={"activity_id": "A-2009", "strategy": "split"},
                ok=True, result_summary="feasible: 2 h + 4 h, 0.5 d float consumed", latency_ms=8)],
            proposal=Proposal(
                kind=ProposalKind.SPLIT, activity_ids=["A-2009"],
                rationale="The pour holds a city-inspector hold point and cannot move, but the "
                          "coating can run in two passes without breaching recoat limits. "
                          "Splitting keeps both inside the 05:00-10:00 window and spends only "
                          "half a day of float.",
                solver_payload={"segments": [{"start": "2026-08-24T05:00:00-07:00", "hours": 2.0},
                                             {"start": "2026-08-24T08:00:00-07:00", "hours": 4.0}],
                                "feasible": True},
                float_days_consumed=0.5, projected_verdict="compliant"),
        ),
        AgentStep(
            seq=4, type=StepType.GATE, at=_at(6.2), conflict_id="C1",
            title="Gate: approve the split",
            detail="Policy engine approved — float consumed is under the near-critical cap.",
            activity_ids=["A-2009"], gate=GATE_APPROVE_SPLIT,
        ),
        AgentStep(
            seq=5, type=StepType.ACT, at=_at(6.4), conflict_id="C1",
            title="Split A-2009 into two passes",
            detail="Applied the approved split via the gated tool.",
            activity_ids=["A-2009"],
            tool_calls=[ToolCall(
                tool=ToolName.SPLIT_ACTIVITY, args={"activity_id": "A-2009", "segments": 2},
                ok=True, gated=True, result_summary="A-2009 split into A-2009a (2 h) + A-2009b (4 h)",
                latency_ms=22)],
            record_seq=101,
        ),
        AgentStep(
            seq=6, type=StepType.VERIFY, at=_at(6.6), conflict_id="C1",
            title="Verify: both activities now compliant",
            detail="Re-evaluated A-2003 and both coating segments against the new plan — all "
                    "sit inside compliant windows.",
            activity_ids=["A-2003", "A-2009"],
            tool_calls=[ToolCall(tool=ToolName.EVALUATE_WINDOW, args={"activity_id": "A-2009b"},
                                 ok=True, result_summary="verdict compliant", latency_ms=11)],
        ),

        # --- Beat (b): the deny case — cheapest fix eats float -> ESCALATE ---
        AgentStep(
            seq=7, type=StepType.PROPOSE, at=_at(9), conflict_id="C2",
            title="Propose: slip the coating to the next clean window",
            detail="The cheapest fix for C2 is to shift the coating a day to the next "
                    "dew-point-compliant window. The solver reports it would push near-critical "
                    "A-2006 and consume four days of its float.",
            activity_ids=["A-2009", "A-2006"],
            tool_calls=[ToolCall(
                tool=ToolName.PROPOSE_RESEQUENCE, args={"activity_id": "A-2009", "strategy": "shift"},
                ok=True, result_summary="feasible but 4.0 d float consumed on near-critical A-2006",
                latency_ms=9)],
            proposal=Proposal(
                kind=ProposalKind.SHIFT, activity_ids=["A-2009"],
                rationale="A one-day slip clears the dew-point conflict cleanly, but it cascades "
                          "onto the near-critical deck weld and burns four days of float — more "
                          "than policy allows an unattended agent to spend. Flagging the tradeoff "
                          "rather than taking it.",
                solver_payload={"new_start": "2026-08-25T05:00:00-07:00", "cascade": ["A-2006"],
                                "feasible": True},
                float_days_consumed=4.0, projected_verdict="compliant"),
        ),
        AgentStep(
            seq=8, type=StepType.GATE, at=_at(9.2), conflict_id="C2",
            title="Gate: deny — over the float cap",
            detail=f"Policy rule {RULE_MAX_FLOAT} caps float consumption at 3.0 d for a "
                   "near-critical activity; this proposal spends 4.0 d. Denied and routed to a human.",
            activity_ids=["A-2009", "A-2006"], gate=GATE_DENY_ESCALATE,
        ),
        AgentStep(
            seq=9, type=StepType.ESCALATE, at=_at(9.5), conflict_id="C2",
            title="Escalate to the superintendent",
            detail="No compliant sequence preserves the milestone without spending more float "
                   "than policy permits. Options handed up: (1) accept the 4 d float hit, "
                   "(2) authorise a dehumidified enclosure to coat in place, (3) an RFI to relax "
                   "the recoat window. Rule cited: " + RULE_MAX_FLOAT + ".",
            activity_ids=["A-2009", "A-2006"],
            tool_calls=[ToolCall(
                tool=ToolName.ESCALATE_TO_SUPERINTENDENT,
                args={"conflict_id": "C2", "options": 3}, ok=True, gated=True,
                result_summary="escalation drafted with three costed options and the rule cited",
                latency_ms=18)],
            record_seq=102,
        ),
        AgentStep(
            seq=10, type=StepType.RECORD, at=_at(9.7),
            title="Appended the run to the record",
            detail="Two record entries written to the hash chain: the approved split and the "
                    "escalation. A claims consultant can re-derive both from the FortyGuard handles.",
            tool_calls=[ToolCall(tool=ToolName.WRITE_RECORD, args={"entries": 2}, ok=True,
                                 gated=True, result_summary="record seq 101, 102 appended", latency_ms=6)],
            record_seq=102,
        ),
    ]

    return AgentRun(
        run_id=RUN_ID, site_id=SITE_ID, started_at=RUN_START, finished_at=_at(10),
        status=RunStatus.COMPLETED, model_name=MODEL_NAME, lookahead_h=72, tier="commit",
        scanned_count=328, flagged_count=41, conflicts_count=2, resolved_count=1, escalated_count=1,
        conflicts=[CONFLICT_POUR_COAT, CONFLICT_COAT_WELD], steps=steps, replay=True,
    )


def build_gate_verdicts() -> list[GateVerdict]:
    """A small deck of gate rulings for the escalation UI: approve, modify, and the
    deny-and-escalate beat. Every rule has a test (tests/test_policy.py, Day 6)."""
    return [GATE_APPROVE_SPLIT, GATE_MODIFY_SHIFT, GATE_DENY_ESCALATE]


def main() -> int:
    ap = argparse.ArgumentParser(description="WORKFACE Day-5 agent-trace fixtures (T3)")
    ap.add_argument("--out", default="data/fixtures", type=Path)
    ap.add_argument("--check", action="store_true", help="validate and print a summary")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    run = build_run()
    verdicts = build_gate_verdicts()

    run_text = run.model_dump_json(indent=2)
    AgentRun.model_validate_json(run_text)                      # must not raise
    (args.out / "sample_agent_run.json").write_text(run_text + "\n", encoding="utf-8")

    verdicts_text = json.dumps([v.model_dump(mode="json") for v in verdicts], indent=2)
    for v in json.loads(verdicts_text):
        GateVerdict.model_validate(v)                           # must not raise
    (args.out / "sample_gate_verdicts.json").write_text(verdicts_text + "\n", encoding="utf-8")

    # Belt-and-braces re-read from disk.
    AgentRun.model_validate_json((args.out / "sample_agent_run.json").read_text(encoding="utf-8"))

    print(f"[ok] sample_agent_run.json      {len(run.steps)} steps, "
          f"{run.conflicts_count} conflicts, {run.resolved_count} resolved, "
          f"{run.escalated_count} escalated")
    print(f"[ok] sample_gate_verdicts.json  {len(verdicts)} verdicts "
          f"({', '.join(v.decision.value for v in verdicts)})")
    if args.check:
        assert run.resolved_count == 1 and run.escalated_count == 1
        assert any(s.type is StepType.ESCALATE for s in run.steps), "expected an escalate step"
        assert any(v.decision is GateDecision.DENY and v.escalated for v in verdicts), "expected a deny+escalate"
        assert any(s.proposal and s.proposal.kind is ProposalKind.SPLIT for s in run.steps), "expected a split"
        print("[ok] --check assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
