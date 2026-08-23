"""
WORKFACE — Day-8 tool-surface tests.  T3, Task F (§4.2).

The point of this suite (§9): a gated, irreversible tool CANNOT be reached without
an APPROVING GateVerdict. shift/split/notify each raise GateError on a missing or
non-approve verdict, and only run on approve. Non-gated tools run freely. No model.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from apps.api.agent import tools
from apps.api.agent.tools import GateError
from packages.schemas.agent_trace import GateDecision, GateVerdict, ToolName
from packages.schemas.record import RecordPayload, GENESIS_PREV_HASH

TZ = timezone(timedelta(hours=-7))
_APPROVE = GateVerdict(decision=GateDecision.APPROVE, rule_id="within_policy", reason="ok", escalated=False)
_DENY = GateVerdict(decision=GateDecision.DENY, rule_id="no_move_past_milestone",
                    reason="would breach MS-340", escalated=True)


def _start():
    return datetime(2026, 8, 25, 7, 0, tzinfo=TZ)


# --------------------------------------------------------------------------- #
# The three gated tools are unreachable without an approving verdict
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("call", [
    lambda: tools.shift_activity(activity_id="A-1", new_start=_start(), verdict=None),
    lambda: tools.split_activity(activity_id="A-1", parts=[{}], verdict=None),
    lambda: tools.notify_crew(activity_id="A-1", crew="coating", message="go", verdict=None),
])
def test_gated_tool_without_verdict_raises(call):
    with pytest.raises(GateError):
        call()


@pytest.mark.parametrize("call", [
    lambda: tools.shift_activity(activity_id="A-1", new_start=_start(), verdict=_DENY),
    lambda: tools.split_activity(activity_id="A-1", parts=[{}], verdict=_DENY),
    lambda: tools.notify_crew(activity_id="A-1", crew="coating", message="go", verdict=_DENY),
])
def test_gated_tool_with_deny_verdict_raises(call):
    with pytest.raises(GateError):
        call()


def test_gated_tools_run_on_approve():
    r = tools.shift_activity(activity_id="A-1237", new_start=_start(), verdict=_APPROVE)
    assert r["tool"] == ToolName.SHIFT_ACTIVITY.value and r["gate_rule_id"] == "within_policy"
    r2 = tools.split_activity(activity_id="A-1237", parts=[{"start": "x"}, {"start": "y"}], verdict=_APPROVE)
    assert r2["tool"] == ToolName.SPLIT_ACTIVITY.value and "2 parts" in r2["summary"]
    r3 = tools.notify_crew(activity_id="A-1237", crew="coating", message="go", verdict=_APPROVE)
    assert r3["tool"] == ToolName.NOTIFY_CREW.value


def test_require_approval_is_the_single_choke_point():
    with pytest.raises(GateError):
        tools.require_approval(ToolName.SHIFT_ACTIVITY, None)
    with pytest.raises(GateError):
        tools.require_approval(ToolName.SHIFT_ACTIVITY, _DENY)
    assert tools.require_approval(ToolName.SHIFT_ACTIVITY, _APPROVE) is _APPROVE


# --------------------------------------------------------------------------- #
# Non-gated tools run freely
# --------------------------------------------------------------------------- #

def test_raise_rfi_and_escalate_need_no_verdict():
    rfi = tools.raise_rfi(activity_id="A-1265", subject="Out-of-spec discharge temp",
                          question="Accept placement above 35 C at discharge?")
    assert rfi["to"] == "Engineer of Record"
    esc = tools.escalate_to_superintendent(activity_id="A-1205", note="hold point; tried shift (denied)")
    assert esc["to"] == "Superintendent"


def test_request_mitigation_uses_site_systems():
    r = tools.request_mitigation(mitigation_id="shade_temporary", when="2026-08-25T14:00:00-07:00",
                                 trade_id="coating_epoxy_structural_steel", work_face_id="WF-FAB2-07")
    assert r["tool"] == ToolName.REQUEST_MITIGATION.value
    assert "ok" in r


def test_get_trade_window_returns_constraints_and_citation():
    tw = tools.get_trade_window("coating_epoxy_structural_steel")
    assert tw["standard_ref"] and len(tw["citation"]) >= 20
    assert any(c["id"] == "offset_dew_point" for c in tw["constraints"])


def test_get_schedule_context_finds_downstream_milestone():
    from apps.api.agent.loop import _load_activities, _load_precedences
    ctx = tools.get_schedule_context("A-1237", _load_activities(), _load_precedences())
    assert "A-1236" in ctx["predecessors"]
    assert "A-1238" in ctx["successors"]
    assert any("MS-340" in (m["milestone_name"] or "") for m in ctx["downstream_milestones"])


def test_write_record_appends_a_linked_entry():
    ev_payload = RecordPayload(
        run_id="t", ts=datetime(2026, 8, 24, 8, 0, tzinfo=TZ), activity_id="A-1",
        activity_name="x", trade_id="t", trade_display_name="T", work_face_id="WF",
        work_face_name="Face", verdict="compliant",
        clause_cited="A clause long enough to be checkable by a human", standard_ref="STD 1",
        action="evaluate")
    entry = tools.write_record(ev_payload, GENESIS_PREV_HASH, 0)
    assert entry.seq == 0 and entry.prev_hash == GENESIS_PREV_HASH and entry.verify()
