"""Fixture acceptance — the committed fixtures validate and tell the demo's story.

Day 4.5: the window-eval fixtures are now REAL `evaluate_window` output over the
synthetic thermal twin, run against schedule rows that exist. So the assertions
below are invariants that survive real output — every activity_id resolves, no
state is hand-drawn — not hand-computed arithmetic against a fabrication.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from apps.api.windows.registry import load_registry
from packages.schemas.agent_trace import AgentRun, GateDecision, GateVerdict, ProposalKind, StepType
from packages.schemas.thermal_series import WorkFaceThermalSeries
from packages.schemas.window_eval import WindowEval, WindowEvalBundle

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures"
DEMO = Path(__file__).resolve().parents[1] / "data" / "project_demo"
SITE_CREW_LANE_ID = "SITE-CREW-HEAT"


@pytest.fixture(scope="module")
def hero() -> WindowEval:
    return WindowEval.model_validate_json((FIXTURES / "sample_window_eval.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def bundle() -> WindowEvalBundle:
    return WindowEvalBundle.model_validate_json(
        (FIXTURES / "sample_window_eval_ribbon.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def activities() -> dict:
    raw = json.loads((DEMO / "activities.json").read_text(encoding="utf-8"))
    return {a["id"]: a for a in raw["activities"]}


def test_hero_is_the_real_bare_deck_coating_lane(hero: WindowEval) -> None:
    """Re-pointed to the REAL A-1069 (bare deck WF-FAB2-07, 25 Aug), pulled from the
    Task-B run. NOTE (reported): its daytime bar comes back `compliant`, and the
    lane-level binding falls back to the first constraint because nothing closes on
    the bar — the dawn dew-point thinning lives in the pre-dawn ribbon cells, not
    the verdict. Assert what is true, not what the Day-1 fabrication claimed."""
    assert hero.activity_id == "A-1069"
    assert hero.trade_id == "coating_epoxy_structural_steel"
    assert hero.work_face_id == "WF-FAB2-07"          # bare FAB2 L2 deck
    assert len(hero.hours) == 72
    assert hero.horizon.step_minutes == 60
    assert hero.verdict.value == "compliant"          # daytime bar clears; see the report
    if hero.binding_constraint is not None:
        trade = load_registry().get(hero.trade_id)
        ids = {c.constraint_id for c in trade.constraints}
        assert hero.binding_constraint.constraint_id in ids


def test_no_cell_state_is_hand_drawn_binding_ids_are_real(bundle: WindowEvalBundle) -> None:
    """The Day-4.5 invariant that replaces the hand-computed surf-dew arithmetic:
    every non-open cell names a binding_constraint_id that exists on that trade in
    the registry; every open cell names none; a cell with a margin names a unit."""
    reg = load_registry()
    ids_by_trade = {t.trade_id: {c.constraint_id for c in t.constraints} for t in reg.all()}
    for ev in bundle.evaluations:
        valid = ids_by_trade[ev.trade_id]
        for cell in ev.hours:
            if cell.state.value == "open":
                assert cell.binding_constraint_id is None
            else:
                assert cell.binding_constraint_id in valid, (ev.activity_id, cell.binding_constraint_id)
            if cell.margin is not None:
                assert cell.margin_unit is not None


def test_bundle_is_38_lanes_9_trades_72_hours(bundle: WindowEvalBundle) -> None:
    assert len(bundle.evaluations) == 38
    trades = {ev.trade_id for ev in bundle.evaluations}
    assert len(trades) == 9, f"expected 9 distinct trades, got {sorted(trades)}"
    for ev in bundle.evaluations:
        assert len(ev.hours) == 72


def test_every_activity_id_resolves_against_the_schedule(bundle: WindowEvalBundle, activities: dict) -> None:
    """The single most valuable line today: no lane can silently join to a row that
    is not there. The one exception is the site-wide crew-heat lane, which is
    deliberately not a schedule row."""
    for ev in bundle.evaluations:
        if ev.activity_id == SITE_CREW_LANE_ID:
            assert ev.work_face_id == "SITE"          # visibly not an activity row
            continue
        row = activities.get(ev.activity_id)
        assert row is not None, f"{ev.activity_id} is not in activities.json"
        assert row["trade_id"] == ev.trade_id
        assert row["work_face_id"] == ev.work_face_id


def test_site_crew_heat_lane_never_closes(bundle: WindowEvalBundle) -> None:
    site = next(ev for ev in bundle.evaluations if ev.activity_id == SITE_CREW_LANE_ID)
    assert site.trade_id == "crew_heat_exposure"
    assert all(c.state.value != "closed" for c in site.hours)   # heat shrinks, never closes


def test_contended_hours_are_a_subset_of_the_horizon(bundle: WindowEvalBundle) -> None:
    lo, hi = bundle.horizon.start, bundle.horizon.end
    assert all(lo <= t < hi for t in bundle.contended_hours)


def test_totals_equal_the_sum_of_the_lanes(bundle: WindowEvalBundle) -> None:
    assert bundle.totals is not None
    at_risk = sum(ev.usd_exposure.at_risk_usd for ev in bundle.evaluations)
    protected = sum(ev.usd_exposure.protected_usd for ev in bundle.evaluations)
    assert bundle.totals.at_risk_usd == pytest.approx(at_risk, abs=1.0)
    assert bundle.totals.protected_usd == pytest.approx(protected, abs=1.0)


def test_thermal_series_validates() -> None:
    series = WorkFaceThermalSeries.model_validate_json(
        (FIXTURES / "sample_thermal_series.json").read_text(encoding="utf-8"))
    assert series.work_face_id == "WF-FAB2-11"
    assert len(series.points) == 72
    # the air curve is unchanged: same Phoenix August diurnal, extended to 72 h
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
