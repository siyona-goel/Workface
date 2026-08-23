"""
WORKFACE — Day-7 policy gate tests.  T3, Task E (§4.3, §8).

One test per rule, all eight, plus the four beats the brief singles out:
  * the DENY case by id (A-1237) — THE Day-7 gate, it does not slide (§8);
  * the APPROVE case — a split of A-1237 returns approve/split_within_float_ok;
  * the hold-point case — any move of A-1205 denies, independent of float;
  * the float-FRACTION hole (§6.1) — 100% of a 0.6 d float denies.

The gate never calls a model (hard rule 4): every Proposal / GateContext here is
built directly. CI runs this suite with LLM_BASE_URL unset.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apps.api.agent.policy import (
    GateContext,
    MilestoneRisk,
    PolicyConfig,
    evaluate_policy,
    load_policy,
)
from packages.schemas.agent_trace import GateDecision, Proposal, ProposalKind

TZ = timezone(timedelta(hours=-7))          # America/Phoenix, no DST
CFG = PolicyConfig()                          # the defaults; matches config/policy.yaml


def _dt(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, day, hour, minute, tzinfo=TZ)


def _proposal(kind: ProposalKind, ids: list[str], float_d: float = 0.0) -> Proposal:
    return Proposal(kind=kind, activity_ids=ids, rationale="test", float_days_consumed=float_d)


# --------------------------------------------------------------------------- #
# One test per rule (all eight)
# --------------------------------------------------------------------------- #

def test_rule_fail_closed_on_stale_forecast():
    ctx = GateContext(kind=ProposalKind.SHIFT, activity_ids=["A-1"], forecast_age_h=5.0)
    v = evaluate_policy(_proposal(ProposalKind.SHIFT, ["A-1"]), ctx, CFG)
    assert v.decision is GateDecision.DENY and v.rule_id == "fail_closed_on_stale_forecast" and v.escalated
    # missing series (age None) also fails closed
    ctx2 = GateContext(kind=ProposalKind.SHIFT, activity_ids=["A-1"], forecast_age_h=None)
    assert evaluate_policy(_proposal(ProposalKind.SHIFT, ["A-1"]), ctx2, CFG).rule_id == "fail_closed_on_stale_forecast"


def test_rule_no_precedence_violation():
    ctx = GateContext(kind=ProposalKind.SHIFT, activity_ids=["A-1"], forecast_age_h=0.5,
                      breaks_precedence=True, precedence_detail="A-1 would start before its cure finishes")
    v = evaluate_policy(_proposal(ProposalKind.SHIFT, ["A-1"]), ctx, CFG)
    assert v.decision is GateDecision.DENY and v.rule_id == "no_precedence_violation" and v.escalated


def test_rule_no_move_inspection_hold_point():
    ctx = GateContext(kind=ProposalKind.SHIFT, activity_ids=["A-1205"], forecast_age_h=0.5,
                      hold_point="City of Phoenix inspector — reinforcing & embed inspection prior to pour")
    v = evaluate_policy(_proposal(ProposalKind.SHIFT, ["A-1205"]), ctx, CFG)
    assert v.decision is GateDecision.DENY and v.rule_id == "no_move_inspection_hold_point"


def test_rule_no_move_past_milestone():
    ms = MilestoneRisk("A-1238", "MS-340 Substation energisation (utility coordinated)",
                       _dt(28, 12, 42), projected_date=_dt(28, 21, 6))
    ctx = GateContext(kind=ProposalKind.SHIFT, activity_ids=["A-1237"], forecast_age_h=0.5,
                      milestones=[ms])
    v = evaluate_policy(_proposal(ProposalKind.SHIFT, ["A-1237"]), ctx, CFG)
    assert v.decision is GateDecision.DENY and v.rule_id == "no_move_past_milestone" and v.escalated


def test_rule_no_out_of_spec_application():
    ctx = GateContext(kind=ProposalKind.SHIFT, activity_ids=["A-1"], forecast_age_h=0.5,
                      out_of_spec=True, out_of_spec_detail="surface below dew point + 2.8 C at the proposed hour")
    v = evaluate_policy(_proposal(ProposalKind.SHIFT, ["A-1"]), ctx, CFG)
    assert v.decision is GateDecision.DENY and v.rule_id == "no_out_of_spec_application"
    # ...but an RFI is the sanctioned path, so it must NOT be caught by this rule.
    rfi_ctx = GateContext(kind=ProposalKind.RFI, activity_ids=["A-1"], forecast_age_h=0.5, out_of_spec=True)
    assert evaluate_policy(_proposal(ProposalKind.RFI, ["A-1"]), rfi_ctx, CFG).decision is GateDecision.APPROVE


def test_rule_max_float_days_consumed_absolute():
    ctx = GateContext(kind=ProposalKind.SHIFT, activity_ids=["A-1"], forecast_age_h=0.5,
                      is_near_critical=True, float_days_consumed=4.0, activity_total_float_d=10.0)
    v = evaluate_policy(_proposal(ProposalKind.SHIFT, ["A-1"], 4.0), ctx, CFG)
    assert v.decision is GateDecision.DENY and v.rule_id == "max_float_days_consumed" and v.escalated
    assert "3" in v.reason        # names the 3.0 d cap that fired


def test_rule_no_auto_night_work():
    ctx = GateContext(kind=ProposalKind.SHIFT, activity_ids=["A-1"], forecast_age_h=0.5,
                      placement_start=_dt(25, 21, 0))     # 21:00 — night
    v = evaluate_policy(_proposal(ProposalKind.SHIFT, ["A-1"]), ctx, CFG)
    assert v.decision is GateDecision.DENY and v.rule_id == "no_auto_night_work"


def test_rule_wbgt_rest_ratio_escalate():
    ctx = GateContext(kind=ProposalKind.SHIFT, activity_ids=["A-1"], forecast_age_h=0.5,
                      placement_start=_dt(25, 13, 0), wbgt_work_fraction=0.25)   # 75% rest band
    v = evaluate_policy(_proposal(ProposalKind.SHIFT, ["A-1"]), ctx, CFG)
    assert v.decision is GateDecision.DENY and v.rule_id == "wbgt_rest_ratio_escalate"


# --------------------------------------------------------------------------- #
# The four beats the brief singles out
# --------------------------------------------------------------------------- #

def test_DENY_CASE_A1237_is_the_day7_gate():
    """A-1237: a shift that consumes its 0.6 d float AND pushes A-1238 past MS-340
    must DENY, escalate, and name the rule that caught it. THIS DOES NOT SLIDE."""
    # A shift that eats all 0.6 d of float (14.4 h) pushes A-1238's 28 Aug 06:42
    # finish to 28 Aug 21:06 — past the 28 Aug 12:42 utility-coordinated milestone.
    ms = MilestoneRisk("A-1238", "MS-340 Substation energisation (utility coordinated)",
                       _dt(28, 12, 42), projected_date=_dt(28, 21, 6))
    ctx = GateContext(
        kind=ProposalKind.SHIFT, activity_ids=["A-1237"], forecast_age_h=0.5,
        is_near_critical=True, float_days_consumed=0.6, activity_total_float_d=0.6,
        milestones=[ms],
    )
    v = evaluate_policy(_proposal(ProposalKind.SHIFT, ["A-1237"], 0.6), ctx, CFG)
    assert v.decision is GateDecision.DENY
    assert v.escalated is True
    assert v.rule_id in {"no_move_past_milestone", "max_float_days_consumed"}
    # The reason is on stage — it must read like a human wrote it, not "policy denied".
    assert "policy denied" not in v.reason.lower()
    assert len(v.reason) > 40
    print("\nA-1237 DENY reason:", v.reason)      # surfaced in -s for the report (§16.1)


def test_APPROVE_CASE_split_of_A1237():
    """A split of A-1237 that keeps both halves compliant and within float returns
    approve with split_within_float_ok — the id T1's UI already uses."""
    ctx = GateContext(
        kind=ProposalKind.SPLIT, activity_ids=["A-1237"], forecast_age_h=0.5,
        is_near_critical=True, float_days_consumed=0.3, activity_total_float_d=0.6,
        milestones=[],   # a split within float breaches no milestone
    )
    v = evaluate_policy(_proposal(ProposalKind.SPLIT, ["A-1237"], 0.3), ctx, CFG)
    assert v.decision is GateDecision.APPROVE
    assert v.rule_id == "split_within_float_ok"


def test_HOLD_POINT_CASE_A1205_independent_of_float():
    """Any move of A-1205 denies on the hold point even with 105 d of float —
    float pressure is irrelevant to an inspection gate."""
    ctx = GateContext(
        kind=ProposalKind.SHIFT, activity_ids=["A-1205"], forecast_age_h=0.5,
        is_near_critical=False, float_days_consumed=0.0, activity_total_float_d=105.45,
        hold_point="City of Phoenix inspector — reinforcing & embed inspection prior to pour",
    )
    v = evaluate_policy(_proposal(ProposalKind.SHIFT, ["A-1205"]), ctx, CFG)
    assert v.decision is GateDecision.DENY and v.rule_id == "no_move_inspection_hold_point"


def test_FLOAT_FRACTION_HOLE_100pct_of_0p6d_denies():
    """§6.1: an absolute 3.0 d cap can NEVER fire on a 0.6 d float. Assert that
    spending 100% of that float denies — and that the FRACTIONAL threshold fired,
    not the absolute one. If this only tested a 4-of-10 spend, the hole survives."""
    ctx = GateContext(
        kind=ProposalKind.SHIFT, activity_ids=["A-1237"], forecast_age_h=0.5,
        is_near_critical=True, float_days_consumed=0.6, activity_total_float_d=0.6,
        milestones=[],    # isolate the float rule — no milestone in play
    )
    v = evaluate_policy(_proposal(ProposalKind.SHIFT, ["A-1237"], 0.6), ctx, CFG)
    assert v.decision is GateDecision.DENY and v.rule_id == "max_float_days_consumed"
    # 0.6 d is well under the 3.0 d absolute cap, so the FRACTION is what tripped.
    assert "%" in v.reason
    print("\nfloat-fraction DENY reason:", v.reason)


# --------------------------------------------------------------------------- #
# Config wiring
# --------------------------------------------------------------------------- #

def test_policy_yaml_keeps_the_contract_rule_ids_and_thresholds():
    cfg = load_policy()
    assert cfg.max_float_days_consumed == 3.0
    assert cfg.max_float_fraction_consumed == 1.0     # the §6.1 fractional cap exists
    assert cfg.wbgt_min_work_fraction == 0.5
    assert cfg.forecast_max_age_h == 2.0


def test_clean_shift_within_all_limits_approves():
    ctx = GateContext(kind=ProposalKind.SHIFT, activity_ids=["A-1"], forecast_age_h=0.5,
                      is_near_critical=True, float_days_consumed=1.0, activity_total_float_d=10.0,
                      placement_start=_dt(25, 8, 0), wbgt_work_fraction=1.0)
    v = evaluate_policy(_proposal(ProposalKind.SHIFT, ["A-1"], 1.0), ctx, CFG)
    assert v.decision is GateDecision.APPROVE and not v.escalated
