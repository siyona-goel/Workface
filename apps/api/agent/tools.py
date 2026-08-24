"""
WORKFACE — the agent's tool surface.  T3, Day 8, Task F (§4.2).

    from apps.api.agent.tools import shift_activity, split_activity, notify_crew, ...

The 13-tool surface from WORKFACE_PROJECT_PLAN.md §4.2. The enum is already in
`agent_trace.py`; these are the implementations. Read tools and non-gated actions
run freely; the THREE irreversible tools — `shift_activity`, `split_activity`,
`notify_crew` — CANNOT execute without an APPROVING `GateVerdict` (§4.2, hard
rule 3). `require_approval` enforces it and `tests/test_tools.py` proves a gated
tool cannot be reached without a verdict.

REPLAY-friendly: these tools produce structured results and record material; they
do not mutate a live P6 schedule. Applying to the real schedule is the deployment
integration, out of scope for the demo (advisory, not certifying — §12.5).

# ---------------------------------------------------------------------------
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task
#   fg_activity_id  = a FortyGuard async job handle
# ---------------------------------------------------------------------------
"""

from __future__ import annotations

from datetime import datetime

from apps.api.sequencer.pack import CrewSource, PackActivity, PackResult, pack
from apps.api.windows.registry import Registry, load_registry
from packages.schemas.agent_trace import GateDecision, GateVerdict, ToolName
from packages.schemas.record import RecordEntry, RecordPayload, make_entry


class GateError(RuntimeError):
    """Raised when an irreversible tool is invoked without an APPROVING GateVerdict.
    This is the wall that makes the gate non-optional (§4.2 / hard rule 3)."""


def require_approval(tool: ToolName, verdict: GateVerdict | None) -> GateVerdict:
    """Every gated tool calls this FIRST. No verdict, or a non-approve verdict, is
    a hard stop — a gated tool can never run on the agent's say-so alone."""
    if verdict is None:
        raise GateError(f"{tool.value} is a gated, irreversible tool and requires a GateVerdict — none was supplied")
    if verdict.decision is not GateDecision.APPROVE:
        raise GateError(
            f"{tool.value} refused: the gate returned {verdict.decision.value} "
            f"({verdict.rule_id}) — {verdict.reason}"
        )
    return verdict


# --------------------------------------------------------------------------- #
# Read tools
# --------------------------------------------------------------------------- #

def get_trade_window(trade_id: str, registry: Registry | None = None) -> dict:
    """The trade's constraint set + citation, for the model's context. Read-only."""
    reg = registry or load_registry()
    trade = reg.get(trade_id)
    return {
        "trade_id": trade_id,
        "display_name": trade.display_name,
        "standard_ref": trade.standard_ref,
        "citation": trade.citation,
        "constraints": [{"id": c.constraint_id, "type": c.type, "label": c.label} for c in trade.constraints],
        "registry_version": reg.version,
    }


def get_schedule_context(activity_id: str, activities: list[dict], precedences: list[dict]) -> dict:
    """Predecessors, successors and any downstream milestone for one activity.
    Read-only — this is what the PROPOSE step reasons over, never mutates."""
    by_id = {a["id"]: a for a in activities}
    preds = [p["pred_id"] for p in precedences if p["activity_id"] == activity_id]
    succs = [p["activity_id"] for p in precedences if p["pred_id"] == activity_id]
    milestones = [
        {"activity_id": s, "milestone_name": by_id[s].get("milestone_name"),
         "milestone_date": by_id[s].get("milestone_date")}
        for s in succs if s in by_id and by_id[s].get("milestone_date")
    ]
    a = by_id.get(activity_id, {})
    return {
        "activity_id": activity_id,
        "predecessors": preds,
        "successors": succs,
        "downstream_milestones": milestones,
        "hold_point": a.get("hold_point"),
        "total_float_d": a.get("total_float_d"),
        "is_near_critical": a.get("is_near_critical"),
    }


# --------------------------------------------------------------------------- #
# propose_resequence — the deterministic solver (Task A). NOT the LLM, NOT gated.
# --------------------------------------------------------------------------- #

def propose_resequence(activities: list[PackActivity], *, crew: CrewSource | None = None,
                       anchor: datetime | None = None) -> PackResult:
    """The greedy packer does the arithmetic the model must never do (§8.2)."""
    return pack(activities, crew=crew, anchor=anchor)


# --------------------------------------------------------------------------- #
# Gated, irreversible actions — every one goes through require_approval FIRST.
# --------------------------------------------------------------------------- #

def shift_activity(*, activity_id: str, new_start: datetime, new_finish: datetime | None = None,
                   verdict: GateVerdict | None = None) -> dict:
    require_approval(ToolName.SHIFT_ACTIVITY, verdict)
    return {
        "tool": ToolName.SHIFT_ACTIVITY.value, "activity_id": activity_id,
        "new_start": new_start.isoformat(), "new_finish": new_finish.isoformat() if new_finish else None,
        "gate_rule_id": verdict.rule_id,
        "summary": f"shifted {activity_id} to {new_start:%d %b %H:%M} (gate: {verdict.rule_id})",
    }


def split_activity(*, activity_id: str, parts: list[dict], verdict: GateVerdict | None = None) -> dict:
    require_approval(ToolName.SPLIT_ACTIVITY, verdict)
    return {
        "tool": ToolName.SPLIT_ACTIVITY.value, "activity_id": activity_id, "parts": parts,
        "gate_rule_id": verdict.rule_id,
        "summary": f"split {activity_id} into {len(parts)} parts (gate: {verdict.rule_id})",
    }


def notify_crew(*, activity_id: str, crew: str, message: str,
                verdict: GateVerdict | None = None) -> dict:
    require_approval(ToolName.NOTIFY_CREW, verdict)
    return {
        "tool": ToolName.NOTIFY_CREW.value, "activity_id": activity_id, "crew": crew,
        "message": message, "gate_rule_id": verdict.rule_id,
        "summary": f"notified {crew} re {activity_id} (gate: {verdict.rule_id})",
    }


# --------------------------------------------------------------------------- #
# Non-gated actions
# --------------------------------------------------------------------------- #

def request_mitigation(*, mitigation_id: str, when: datetime | str, trade_id: str | None = None,
                       work_face_id: str | None = None, systems=None, **kwargs) -> dict:
    """Check availability via T2's MockSiteSystems (already merged, §5) before
    proposing. Not gated — a mitigation is a request, not an irreversible move."""
    if systems is None:
        from apps.api.sitefeeds.sitesystems import MockSiteSystems
        systems = MockSiteSystems()
    res = systems.can_request_mitigation(
        mitigation_id, when=when, trade_id=trade_id, work_face_id=work_face_id, **kwargs)
    res["tool"] = ToolName.REQUEST_MITIGATION.value
    res["summary"] = f"{'requested' if res['ok'] else 'blocked'} {mitigation_id}: {res['reason']}"
    return res


def raise_rfi(*, activity_id: str, subject: str, question: str,
              to: str = "Engineer of Record") -> dict:
    """The ONLY sanctioned path to accept out-of-spec work (§4.2). Not gated —
    raising an RFI does not move a crew; it asks the EOR to decide."""
    return {
        "tool": ToolName.RAISE_RFI.value, "activity_id": activity_id, "to": to,
        "subject": subject, "question": question,
        "summary": f"RFI to {to} re {activity_id}: {subject}",
    }


def escalate_to_superintendent(*, activity_id: str, note: str,
                               to: str = "Superintendent") -> dict:
    """Human in the loop. `note` must state what was tried, what each attempt would
    cost, and why no option was acceptable (§9) — not 'escalating for review'."""
    return {
        "tool": ToolName.ESCALATE_TO_SUPERINTENDENT.value, "activity_id": activity_id,
        "to": to, "note": note,
        "summary": f"escalated {activity_id} to {to}",
    }


# --------------------------------------------------------------------------- #
# write_record — append-only (hard rule 5)
# --------------------------------------------------------------------------- #

def write_record(payload: RecordPayload, prev_hash: str, seq: int) -> RecordEntry:
    """Append one entry via the canonical `make_entry`. There is no update or
    delete path, by design — the chain is the warranty defence."""
    return make_entry(payload, prev_hash, seq)


__all__ = [
    "GateError", "require_approval",
    "get_trade_window", "get_schedule_context", "propose_resequence",
    "shift_activity", "split_activity", "notify_crew",
    "request_mitigation", "raise_rfi", "escalate_to_superintendent",
    "write_record",
]
