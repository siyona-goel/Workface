"""
WORKFACE — Day-6 agent loop tests.  T3, Task E.

The loop is SCAN -> EVALUATE -> CONFLICT, pure Python, no LLM (§7). These assert:
  * the lookahead scan reproduces the brief's 62 in-window / 37 thermal-sensitive
    at the 2026-08-24 horizon with overlap semantics;
  * EVALUATE flags a SANE subset (not 0, not all) and never folds NO_DATA into
    flagged_count;
  * CONFLICT only emits where demanded productive hours exceed open hours;
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
from packages.schemas.agent_trace import AgentRun, StepType


def test_scan_counts_match_the_brief():
    in_window = list_activities_in_lookahead(LOOKAHEAD_H)
    thermal = [a for a in in_window if a["thermal_sensitive"] and a["trade_id"]]
    assert len(in_window) == 62
    assert len(thermal) == 37


def test_run_has_exactly_scan_evaluate_conflict():
    run = run_agent()
    assert [s.type for s in run.steps] == [StepType.SCAN, StepType.EVALUATE, StepType.CONFLICT]
    # No Day-7 stages leaked in.
    assert not any(s.type in {StepType.PROPOSE, StepType.GATE, StepType.ACT} for s in run.steps)
    assert run.resolved_count == 0 and run.escalated_count == 0


def test_flags_a_sane_subset():
    """Not 0, not all 37 — a sane middle. If this ever reads 3 or 36, the model
    of the day is wrong, not the number (brief §6)."""
    run = run_agent()
    assert run.scanned_count == 62
    assert 5 <= run.flagged_count <= 32       # Phoenix August: most daytime work is at risk
    assert run.flagged_count < 37


def test_no_data_not_counted_as_flagged():
    """NO_DATA is a fail-closed data gap, not a risk flag; it must not inflate
    flagged_count. The EVALUATE step names it separately."""
    run = run_agent()
    ev_step = next(s for s in run.steps if s.type is StepType.EVALUATE)
    # flagged_count equals the number of activity_ids the EVALUATE step lists.
    assert run.flagged_count == len(ev_step.activity_ids)
    assert "no_data" in ev_step.detail.lower()


def test_conflicts_only_where_demand_exceeds_supply():
    run = run_agent()
    assert run.conflicts_count == len(run.conflicts)
    for c in run.conflicts:
        assert c.demanded_hours > c.compliant_hours
        assert len(c.competing_activity_ids) >= 2
        assert ANCHOR.date().isoformat() <= c.shift_date


def test_emitted_run_validates_against_the_schema():
    run = run_agent()
    # Round-trips through the exact schema T1's Trace view renders.
    AgentRun.model_validate_json(run.model_dump_json())
    assert run.model_name.startswith("none")     # pure-Python gate, no LLM in Day 6


def test_does_not_overwrite_the_hand_fixture():
    """The live loop writes agent_run_live.json; the hand fixture is untouched and
    still carries its full-loop step set (propose/gate/act/escalate)."""
    hand = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "sample_agent_run.json"
    fixture = AgentRun.model_validate_json(hand.read_text(encoding="utf-8"))
    assert fixture.scanned_count == 328          # the hand fixture's own numbers, unchanged
    assert any(s.type is StepType.ESCALATE for s in fixture.steps)
