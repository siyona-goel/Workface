"""
WORKFACE — the `agent_trace` contract.

    packages/schemas/agent_trace.py   (this file, Pydantic v2)
    packages/schemas/agent_trace.ts    (Zod — keep field-for-field identical)

Handoff #6 in WORKFACE_SCHEDULE.md: T3 -> T1 (schema + fixtures Day 5, so T1
builds the Trace view Day 6 and the escalation UI Day 7 against fixtures — not
the live loop). This is the AI-Agents track's primary artifact: a replayable
decision log, not a debug dump.

The loop it traces (WORKFACE_TECH_SPEC.md §8.1):

    SCAN     -> list_activities_in_lookahead(72)
    EVALUATE -> get_work_face_thermal -> evaluate_window        [deterministic]
    CONFLICT -> group by work face + shift; find activities competing for hours
    PROPOSE  -> LLM picks a strategy (shift/split/resequence/mitigate/rfi/escalate)
                and calls propose_resequence for the ACTUAL arithmetic
    GATE     -> deterministic policy engine: approve / modify / deny + reason + rule_id
    ACT      -> gated tools only
    VERIFY   -> re-evaluate the affected activities against the new plan
    RECORD   -> append to the hash chain (see record.py)

The physics, the window maths and the sequencing are NEVER the LLM. The model
only chooses a strategy and writes the rationale a human reads (§8.2). The
record entries this run writes are the `record.py` contract (handoffs #6/#7).

# ---------------------------------------------------------------------------
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task (from P6 / the generator)
#   fg_activity_id  = a FortyGuard async job handle (from submit -> /v1/status/{id})
# ---------------------------------------------------------------------------

Changing a field here is a PR that tags T1 and T3. Never rename silently.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = "1.0.0"

Iso8601 = Annotated[
    datetime,
    Field(description="ISO-8601 with offset. Site-local (America/Phoenix, UTC-07:00, no DST)."),
]


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #

class StepType(str, Enum):
    """One stage of the loop. T1 groups and icons the trace off this."""
    SCAN = "scan"
    EVALUATE = "evaluate"
    CONFLICT = "conflict"
    PROPOSE = "propose"
    GATE = "gate"
    ACT = "act"
    VERIFY = "verify"
    RECORD = "record"
    ESCALATE = "escalate"


class ToolName(str, Enum):
    """The 13-tool surface (WORKFACE_PROJECT_PLAN.md §4.2). Gated ones are irreversible."""
    LIST_ACTIVITIES_IN_LOOKAHEAD = "list_activities_in_lookahead"
    GET_WORK_FACE_THERMAL = "get_work_face_thermal"
    GET_TRADE_WINDOW = "get_trade_window"
    EVALUATE_WINDOW = "evaluate_window"
    GET_SCHEDULE_CONTEXT = "get_schedule_context"
    PROPOSE_RESEQUENCE = "propose_resequence"        # deterministic solver, NOT the LLM
    SHIFT_ACTIVITY = "shift_activity"                # gated / irreversible
    SPLIT_ACTIVITY = "split_activity"                # gated / irreversible
    REQUEST_MITIGATION = "request_mitigation"
    RAISE_RFI = "raise_rfi"                          # the only path to accept out-of-spec work
    NOTIFY_CREW = "notify_crew"                      # gated / irreversible
    ESCALATE_TO_SUPERINTENDENT = "escalate_to_superintendent"
    WRITE_RECORD = "write_record"                    # append-only, hash-chained


class ProposalKind(str, Enum):
    """What the LLM chose to attempt. The arithmetic is always the solver's."""
    SHIFT = "shift"
    SPLIT = "split"
    RESEQUENCE = "resequence"
    MITIGATE = "mitigate"
    RFI = "rfi"
    ESCALATE = "escalate"
    NO_ACTION = "no_action"


class GateDecision(str, Enum):
    """The deterministic policy engine's verdict on a proposal (§8.3)."""
    APPROVE = "approve"
    MODIFY = "modify"    # approved with the solver's amended parameters
    DENY = "deny"        # blocked; the reason names the rule and usually escalates


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# --------------------------------------------------------------------------- #
# Leaf models
# --------------------------------------------------------------------------- #

class ToolCall(BaseModel):
    """One tool invocation inside a step. Inputs/outputs summarised for the UI."""
    model_config = ConfigDict(extra="forbid")

    tool: ToolName
    args: dict = Field(default_factory=dict, description="Arguments as called. Small/JSON-safe.")
    ok: bool = True
    gated: bool = Field(False, description="True for irreversible tools that pass through the policy gate.")
    result_summary: str | None = Field(None, max_length=500, description="Human-readable outcome. Not the raw payload.")
    fg_activity_ids: list[str] = Field(
        default_factory=list, description="Any FortyGuard handles this call rested on. NOT activity_id.",
    )
    latency_ms: int | None = Field(None, ge=0)


class GateVerdict(BaseModel):
    """The policy gate's ruling. Rendered verbatim in the escalation UI.

    Mirrors `apps/api/agent/policy.py`'s (proposal, context) -> Verdict. Every
    rule has a test, INCLUDING the deny case (tests/test_policy.py).
    """
    model_config = ConfigDict(extra="forbid")

    decision: GateDecision
    rule_id: str = Field(..., description="Stable id from config/policy.yaml, e.g. 'no_move_past_milestone'.")
    reason: str = Field(..., max_length=500, description="One sentence a superintendent reads. Names the rule's basis.")
    escalated: bool = Field(False, description="True when a deny routes to a human.")
    modified_params: dict | None = Field(
        None, description="For decision=modify: the amended parameters the solver substituted.",
    )


class Proposal(BaseModel):
    """What the agent proposed for a conflict. `rationale` is LLM-written; the numbers are not."""
    model_config = ConfigDict(extra="forbid")

    kind: ProposalKind
    activity_ids: list[str] = Field(..., description="SCHEDULE activities affected. Never FortyGuard handles.")
    rationale: str = Field(..., max_length=1200, description="The LLM's plain-English case. The human-facing 'why'.")
    solver_payload: dict | None = Field(
        None, description="The deterministic propose_resequence output: proposed windows, float consumed, feasibility.",
    )
    float_days_consumed: float | None = Field(None, description="Total float this proposal would spend. Feeds the gate.")
    projected_verdict: str | None = Field(
        None, description="What the affected activities' window_eval verdict becomes if applied (from VERIFY).",
    )


class Conflict(BaseModel):
    """The step that makes it an agent: A's fix breaks B. Contention for scarce hours."""
    model_config = ConfigDict(extra="forbid")

    id: str
    work_face_id: str
    shift_date: str = Field(..., description="YYYY-MM-DD of the contended shift.")
    competing_activity_ids: list[str] = Field(..., min_length=2, description="Activities fighting over the same hours.")
    compliant_hours: float = Field(..., ge=0, description="Open hours available on that face that shift.")
    demanded_hours: float = Field(..., ge=0, description="Sum of productive hours the competing activities need.")
    description: str = Field(..., max_length=400, description="'9 trades want 5 compliant hours' in one sentence.")
    resolved_by_step_seq: int | None = Field(None, description="The AgentStep.seq that resolved or escalated this.")


class AgentStep(BaseModel):
    """One row in the trace. T1 streams these as step cards."""
    model_config = ConfigDict(extra="forbid")

    seq: int = Field(..., ge=0, description="Monotonic within the run. T1 orders on this.")
    type: StepType
    at: Iso8601
    title: str = Field(..., max_length=160, description="Short card heading, e.g. 'Flagged 41 of 300 activities'.")
    detail: str | None = Field(None, max_length=2000, description="Body text. May quote the cited clause.")
    activity_ids: list[str] = Field(default_factory=list, description="Activities this step touched.")
    conflict_id: str | None = Field(None, description="Links a propose/gate/act step to the Conflict it addresses.")
    tool_calls: list[ToolCall] = Field(default_factory=list)
    proposal: Proposal | None = None
    gate: GateVerdict | None = None
    record_seq: int | None = Field(None, description="The record_entry.seq this step appended, if any (record.py).")


class AgentRun(BaseModel):
    """One unattended run of the loop. The unit the Trace view renders."""
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    run_id: str
    site_id: str
    started_at: Iso8601
    finished_at: Iso8601 | None = None
    status: RunStatus = RunStatus.RUNNING

    model_name: str = Field(..., description="The LLM used, e.g. 'llama-3.3-70b-instruct-turbo'. Replay tests both.")
    lookahead_h: int = Field(72, gt=0, description="The rolling horizon the agent scanned.")
    tier: str = Field("commit", description="Which temporal loop this run operated in (plan/commit/record).")

    # --- headline counters the demo narrates -------------------------------
    scanned_count: int = Field(0, ge=0, description="Activities in the lookahead. e.g. 300.")
    flagged_count: int = Field(0, ge=0, description="At-risk after evaluation. e.g. 41.")
    conflicts_count: int = Field(0, ge=0)
    resolved_count: int = Field(0, ge=0, description="Conflicts resolved by an approved action.")
    escalated_count: int = Field(0, ge=0, description="Routed to a human. The 'it knows what it can't do' number.")

    conflicts: list[Conflict] = Field(default_factory=list)
    steps: list[AgentStep] = Field(..., description="The full ordered trace.")

    replay: bool = Field(True, description="True when served from fixtures. REPLAY_MODE default is true.")

    @field_validator("steps")
    @classmethod
    def _steps_ordered(cls, v: list[AgentStep]) -> list[AgentStep]:
        if not v:
            raise ValueError("an agent run must have at least one step")
        for a, b in zip(v, v[1:]):
            if b.seq <= a.seq:
                raise ValueError(f"step seq must be strictly increasing: {a.seq} -> {b.seq}")
        return v


__all__ = [
    "SCHEMA_VERSION", "StepType", "ToolName", "ProposalKind", "GateDecision", "RunStatus",
    "ToolCall", "GateVerdict", "Proposal", "Conflict", "AgentStep", "AgentRun",
]
