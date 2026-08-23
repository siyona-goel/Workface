"""
WORKFACE — agent loop tests.  T3, Task E (Day 6 SCAN/EVALUATE/CONFLICT + Day 7
PROPOSE/GATE/ACT). Run deterministically (use_llm=False) so the suite is stable
and model-free regardless of whether LLM_BASE_URL happens to be set locally; the
LLM path is covered by tests/test_agent_replay.py. These assert:
  * the lookahead scan reproduces the brief's 62 in-window / 37 thermal-sensitive;
  * EVALUATE flags a SANE subset and never folds NO_DATA into flagged_count;
  * CONFLICT only emits where demanded productive hours exceed open hours;
  * the Day-7 stages appear and every gated ACT is preceded by a GATE approval;
  * the emitted AgentRun validates against the SAME schema as the hand fixture,
    and the loop does not overwrite sample_agent_run.json.
"""

from __future__ import annotations

from pathlib import Path

from apps.api.agent.loop import (
    ANCHOR,
    LOOKAHEAD_H,
    list_activities_in_lookahead,
    run_agent,
)
from packages.schemas.agent_trace import AgentRun, GateDecision, ProposalKind, StepType, ToolName

_GATED_TOOLS = {ToolName.SHIFT_ACTIVITY, ToolName.SPLIT_ACTIVITY, ToolName.NOTIFY_CREW}


def test_scan_counts_match_the_brief():
    in_window = list_activities_in_lookahead(LOOKAHEAD_H)
    thermal = [a for a in in_window if a["thermal_sensitive"] and a["trade_id"]]
    assert len(in_window) == 62
    assert len(thermal) == 37


def test_loop_runs_the_full_scan_to_act_pipeline():
    run = run_agent(use_llm=False)
    # The first three stages are still SCAN -> EVALUATE -> CONFLICT, in order.
    assert [s.type for s in run.steps[:3]] == [StepType.SCAN, StepType.EVALUATE, StepType.CONFLICT]
    # Day-7 stages now follow.
    kinds = {s.type for s in run.steps}
    assert StepType.PROPOSE in kinds and StepType.GATE in kinds
    assert StepType.ACT in kinds or StepType.ESCALATE in kinds
    assert run.resolved_count + run.escalated_count > 0


def test_flags_a_sane_subset():
    """Not 0, not all 37 — a sane middle. If this ever reads 3 or 36, the model
    of the day is wrong, not the number (brief §6)."""
    run = run_agent(use_llm=False)
    assert run.scanned_count == 62
    assert 5 <= run.flagged_count <= 32       # Phoenix August: most daytime work is at risk
    assert run.flagged_count < 37


def test_no_data_not_counted_as_flagged():
    """NO_DATA is a fail-closed data gap, not a risk flag; it must not inflate
    flagged_count. The EVALUATE step names it separately."""
    run = run_agent(use_llm=False)
    ev_step = next(s for s in run.steps if s.type is StepType.EVALUATE)
    assert run.flagged_count == len(ev_step.activity_ids)
    assert "no_data" in ev_step.detail.lower()


def test_conflicts_only_where_demand_exceeds_supply():
    run = run_agent(use_llm=False)
    assert run.conflicts_count == len(run.conflicts)
    for c in run.conflicts:
        assert c.demanded_hours > c.compliant_hours
        assert len(c.competing_activity_ids) >= 2
        assert ANCHOR.date().isoformat() <= c.shift_date


def test_every_gated_act_has_a_preceding_gate_approval():
    """§9 / hard rule 3: a gated tool (shift/split/notify) can never be reached
    without a GateVerdict. In the trace, every ACT firing a gated tool is preceded
    by a GATE approval for the same activity."""
    run = run_agent(use_llm=False)
    approved_gated: set[str] = set()
    for s in run.steps:
        if s.type is StepType.GATE and s.gate and s.gate.decision is GateDecision.APPROVE:
            approved_gated.update(s.activity_ids)
        if s.type is StepType.ACT:
            tc = s.tool_calls[0]
            if tc.tool in _GATED_TOOLS:
                assert tc.gated is True
                assert set(s.activity_ids) <= approved_gated, f"{s.activity_ids} acted without a gate approval"


def test_hold_point_activity_escalates_not_resolved():
    """A-1205 carries an inspection hold point; it must escalate, never be quietly
    resolved by a mitigation (§9, the bug the pre-check exists to prevent)."""
    run = run_agent(use_llm=False)
    esc = [s for s in run.steps if s.type is StepType.ESCALATE and "A-1205" in s.activity_ids]
    assert esc, "A-1205 (hold point) must appear as an escalation"
    acted = [s for s in run.steps if s.type is StepType.ACT and "A-1205" in s.activity_ids]
    assert not acted, "A-1205 must not be resolved by an action — it is a human hold point"


def test_emitted_run_validates_against_the_schema():
    run = run_agent(use_llm=False)
    AgentRun.model_validate_json(run.model_dump_json())
    assert run.model_name.startswith("none")     # deterministic proposer; the gate is always pure Python


def test_split_is_attempted_before_shift_in_the_order():
    """Task D: for any activity that reaches both, a SPLIT proposal precedes a
    SHIFT proposal in the trace."""
    run = run_agent(use_llm=False)
    for aid in {a for s in run.steps if s.type is StepType.PROPOSE for a in s.activity_ids}:
        kinds = [s.proposal.kind for s in run.steps
                 if s.type is StepType.PROPOSE and aid in s.activity_ids and s.proposal]
        if ProposalKind.SPLIT in kinds and ProposalKind.SHIFT in kinds:
            assert kinds.index(ProposalKind.SPLIT) < kinds.index(ProposalKind.SHIFT)


def test_does_not_overwrite_the_hand_fixture():
    """The live loop writes agent_run_live.json; the hand fixture is untouched and
    still carries its full-loop step set (propose/gate/act/escalate)."""
    hand = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "sample_agent_run.json"
    fixture = AgentRun.model_validate_json(hand.read_text(encoding="utf-8"))
    assert fixture.scanned_count == 328          # the hand fixture's own numbers, unchanged
    assert any(s.type is StepType.ESCALATE for s in fixture.steps)
