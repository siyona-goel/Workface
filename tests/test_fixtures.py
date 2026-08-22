"""TASK 2 acceptance — the Day-1 fixtures validate and tell the demo's story.

Definition of done (T3_BUILD_BRIEF, Half B):
    sample_window_eval.json and sample_window_eval_ribbon.json both validate
    against packages/schemas/window_eval.py — asserted in a test, not by hand.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.schemas.agent_trace import AgentRun, GateDecision, GateVerdict, ProposalKind, StepType
from packages.schemas.thermal_series import WorkFaceThermalSeries
from packages.schemas.window_eval import WindowEval, WindowEvalBundle

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures"


@pytest.fixture(scope="module")
def hero() -> WindowEval:
    return WindowEval.model_validate_json((FIXTURES / "sample_window_eval.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def bundle() -> WindowEvalBundle:
    return WindowEvalBundle.model_validate_json(
        (FIXTURES / "sample_window_eval_ribbon.json").read_text(encoding="utf-8"))


def test_hero_validates_and_is_the_coating_at_risk_case(hero: WindowEval) -> None:
    assert hero.trade_id == "coating_epoxy_structural_steel"
    assert hero.work_face_id == "WF-FAB2-11"          # bare FAB2 L3 deck
    assert hero.verdict.value == "at_risk"
    assert hero.binding_constraint is not None
    assert hero.binding_constraint.constraint_id == "offset_dew_point"
    assert len(hero.hours) == 48
    assert hero.horizon.step_minutes == 60


def test_hero_per_hour_state_is_consistent_with_values(hero: WindowEval) -> None:
    """The brief's non-negotiable: reason/state/values must agree per hour."""
    for cell in hero.hours:
        surf = cell.values.t_surf_c
        dew = cell.values.t_dew_c
        assert surf is not None and dew is not None
        expected_margin = round(surf - dew - 2.8, 2)
        assert cell.margin == pytest.approx(expected_margin, abs=0.01)
        if expected_margin < 0:
            assert cell.state.value == "closed"
        elif expected_margin < 1.0:
            assert cell.state.value == "marginal"
        else:
            assert cell.state.value == "open"
        # open cells carry no binding id; gated cells name the dew-point offset
        if cell.state.value == "open":
            assert cell.binding_constraint_id is None
        else:
            assert cell.binding_constraint_id == "offset_dew_point"


def test_bundle_is_nine_trades_colliding(bundle: WindowEvalBundle) -> None:
    assert len(bundle.evaluations) == 9
    trades = {ev.trade_id for ev in bundle.evaluations}
    assert len(trades) == 9, f"expected 9 distinct trades, got {sorted(trades)}"
    # every lane is on the 48 h horizon at 60 min steps
    for ev in bundle.evaluations:
        assert len(ev.hours) == 48


def test_bundle_contended_band_is_the_dawn_window(bundle: WindowEvalBundle) -> None:
    assert bundle.contended_hours, "expected a contended dawn window"
    hours = {ts.hour for ts in bundle.contended_hours}
    assert hours == {5, 6, 7, 8, 9}, hours          # 05:00-09:00 both days


def test_hma_is_the_honest_counter_trade(bundle: WindowEvalBundle) -> None:
    """HMA wants the afternoon heat while the others flee it — closed at dawn, open midday."""
    hma = next(ev for ev in bundle.evaluations if ev.trade_id == "hma_paving_surface_course")
    by_hour = {c.ts.hour: c.state.value for c in hma.hours if c.ts.day == 24}
    assert by_hour[5] == "closed"                    # cool dawn: mat would stiffen
    assert by_hour[14] == "open"                     # hot afternoon base: full compaction window


def test_thermal_series_validates() -> None:
    series = WorkFaceThermalSeries.model_validate_json(
        (FIXTURES / "sample_thermal_series.json").read_text(encoding="utf-8"))
    assert series.work_face_id == "WF-FAB2-11"
    assert len(series.points) == 48
    # drivers follow the Phoenix August diurnal the brief specifies
    p05 = next(p for p in series.points if p.ts.hour == 5 and p.ts.day == 24)
    p15 = next(p for p in series.points if p.ts.hour == 15 and p.ts.day == 24)
    assert p05.t_air_c == pytest.approx(29.0)
    assert p15.t_air_c == pytest.approx(42.0)


def test_all_three_fixtures_are_committed_json() -> None:
    for name in ("sample_window_eval.json", "sample_window_eval_ribbon.json", "sample_thermal_series.json"):
        path = FIXTURES / name
        assert path.exists(), f"{name} missing — a fixture on someone's laptop is not a fixture"
        json.loads(path.read_text(encoding="utf-8"))  # well-formed JSON


# --------------------------------------------------------------------------- #
# Day-5 agent-trace fixtures — T1 builds the Trace view and escalation UI on these
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def agent_run() -> AgentRun:
    return AgentRun.model_validate_json((FIXTURES / "sample_agent_run.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def gate_verdicts() -> list[GateVerdict]:
    raw = json.loads((FIXTURES / "sample_gate_verdicts.json").read_text(encoding="utf-8"))
    return [GateVerdict.model_validate(v) for v in raw]


def test_agent_run_validates_and_covers_both_beats(agent_run: AgentRun) -> None:
    assert agent_run.resolved_count == 1 and agent_run.escalated_count == 1
    # Beat (a): a conflict resolved with a split.
    assert any(s.proposal and s.proposal.kind is ProposalKind.SPLIT for s in agent_run.steps)
    # Beat (b): the deny -> escalate case, with a float-based rule named.
    escalate = next(s for s in agent_run.steps if s.type is StepType.ESCALATE)
    deny = next(s for s in agent_run.steps if s.gate and s.gate.decision is GateDecision.DENY)
    assert deny.gate.escalated is True
    assert deny.gate.rule_id == "max_float_days_consumed"
    assert "float" in deny.gate.reason.lower()
    assert escalate.conflict_id == deny.conflict_id


def test_gate_verdicts_cover_approve_modify_deny(gate_verdicts: list[GateVerdict]) -> None:
    decisions = {v.decision for v in gate_verdicts}
    assert decisions == {GateDecision.APPROVE, GateDecision.MODIFY, GateDecision.DENY}
    deny = next(v for v in gate_verdicts if v.decision is GateDecision.DENY)
    assert deny.escalated is True and deny.rule_id  # the deny beat names its rule


def test_agent_fixtures_are_committed_json() -> None:
    for name in ("sample_agent_run.json", "sample_gate_verdicts.json"):
        path = FIXTURES / name
        assert path.exists(), f"{name} missing — a fixture on someone's laptop is not a fixture"
        json.loads(path.read_text(encoding="utf-8"))
