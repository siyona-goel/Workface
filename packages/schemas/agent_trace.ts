/**
 * WORKFACE — the `agent_trace` contract (Zod mirror of agent_trace.py).
 *
 * Handoff #6 in WORKFACE_SCHEDULE.md: T3 -> T1. The replayable agent decision
 * log (SCAN -> EVALUATE -> CONFLICT -> PROPOSE -> GATE -> ACT -> VERIFY ->
 * RECORD). The AI-Agents track's primary artifact — a feature, not a debug dump.
 *
 * Keep this field-for-field identical to packages/schemas/agent_trace.py.
 * Any change is a PR that tags T1 and T3. Never rename a field silently.
 *
 * ---------------------------------------------------------------------------
 * WORKFACE NAMING RULE — do not violate.
 *   activityId / activity_id    = a scheduled construction task
 *   fgActivityId / fg_activity_id = a FortyGuard async job handle
 * ---------------------------------------------------------------------------
 *
 * Wire format is snake_case. Parse as-is.
 */

import { z } from "zod";

export const SCHEMA_VERSION = "1.0.0";

/* -------------------------------------------------------------------------- */
/* Enums                                                                      */
/* -------------------------------------------------------------------------- */

/** One stage of the loop. T1 groups and icons the trace off this. */
export const StepType = z.enum([
  "scan",
  "evaluate",
  "conflict",
  "propose",
  "gate",
  "act",
  "verify",
  "record",
  "escalate",
]);
export type StepType = z.infer<typeof StepType>;

/** The 13-tool surface. Gated ones are irreversible. */
export const ToolName = z.enum([
  "list_activities_in_lookahead",
  "get_work_face_thermal",
  "get_trade_window",
  "evaluate_window",
  "get_schedule_context",
  "propose_resequence",
  "shift_activity",
  "split_activity",
  "request_mitigation",
  "raise_rfi",
  "notify_crew",
  "escalate_to_superintendent",
  "write_record",
]);
export type ToolName = z.infer<typeof ToolName>;

/** What the LLM chose to attempt. The arithmetic is always the solver's. */
export const ProposalKind = z.enum([
  "shift",
  "split",
  "resequence",
  "mitigate",
  "rfi",
  "escalate",
  "no_action",
]);
export type ProposalKind = z.infer<typeof ProposalKind>;

/** The deterministic policy engine's verdict on a proposal. */
export const GateDecision = z.enum(["approve", "modify", "deny"]);
export type GateDecision = z.infer<typeof GateDecision>;

export const RunStatus = z.enum(["running", "completed", "failed"]);
export type RunStatus = z.infer<typeof RunStatus>;

/** ISO-8601 with offset, site-local (America/Phoenix, UTC-07:00, no DST). */
const Iso8601 = z.string().datetime({ offset: true });

/* -------------------------------------------------------------------------- */
/* Leaf models                                                                */
/* -------------------------------------------------------------------------- */

/** One tool invocation inside a step. Inputs/outputs summarised for the UI. */
export const ToolCall = z.object({
  tool: ToolName,
  args: z.record(z.string(), z.unknown()).default({}),
  ok: z.boolean().default(true),
  /** True for irreversible tools that pass through the policy gate. */
  gated: z.boolean().default(false),
  result_summary: z.string().max(500).nullable().default(null),
  /** Any FortyGuard handles this call rested on. NOT activity_id. */
  fg_activity_ids: z.array(z.string()).default([]),
  latency_ms: z.number().int().min(0).nullable().default(null),
});
export type ToolCall = z.infer<typeof ToolCall>;

/** The policy gate's ruling. Rendered verbatim in the escalation UI. */
export const GateVerdict = z.object({
  decision: GateDecision,
  /** Stable id from config/policy.yaml, e.g. 'no_move_past_milestone'. */
  rule_id: z.string(),
  reason: z.string().max(500),
  /** True when a deny routes to a human. */
  escalated: z.boolean().default(false),
  /** For decision=modify: the amended parameters the solver substituted. */
  modified_params: z.record(z.string(), z.unknown()).nullable().default(null),
});
export type GateVerdict = z.infer<typeof GateVerdict>;

/** What the agent proposed for a conflict. rationale is LLM-written; the numbers are not. */
export const Proposal = z.object({
  kind: ProposalKind,
  /** SCHEDULE activities affected. Never FortyGuard handles. */
  activity_ids: z.array(z.string()),
  /** The LLM's plain-English case. The human-facing 'why'. */
  rationale: z.string().max(1200),
  /** The deterministic propose_resequence output. */
  solver_payload: z.record(z.string(), z.unknown()).nullable().default(null),
  float_days_consumed: z.number().nullable().default(null),
  projected_verdict: z.string().nullable().default(null),
});
export type Proposal = z.infer<typeof Proposal>;

/** The step that makes it an agent: A's fix breaks B. Contention for scarce hours. */
export const Conflict = z.object({
  id: z.string(),
  work_face_id: z.string(),
  /** YYYY-MM-DD of the contended shift. */
  shift_date: z.string(),
  competing_activity_ids: z.array(z.string()).min(2),
  compliant_hours: z.number().min(0),
  demanded_hours: z.number().min(0),
  description: z.string().max(400),
  resolved_by_step_seq: z.number().int().nullable().default(null),
});
export type Conflict = z.infer<typeof Conflict>;

/** One row in the trace. T1 streams these as step cards. */
export const AgentStep = z.object({
  seq: z.number().int().min(0),
  type: StepType,
  at: Iso8601,
  title: z.string().max(160),
  detail: z.string().max(2000).nullable().default(null),
  activity_ids: z.array(z.string()).default([]),
  conflict_id: z.string().nullable().default(null),
  tool_calls: z.array(ToolCall).default([]),
  proposal: Proposal.nullable().default(null),
  gate: GateVerdict.nullable().default(null),
  /** The record_entry.seq this step appended, if any (record.ts). */
  record_seq: z.number().int().nullable().default(null),
});
export type AgentStep = z.infer<typeof AgentStep>;

/** One unattended run of the loop. The unit the Trace view renders. */
export const AgentRun = z
  .object({
    schema_version: z.string().default(SCHEMA_VERSION),
    run_id: z.string(),
    site_id: z.string(),
    started_at: Iso8601,
    finished_at: Iso8601.nullable().default(null),
    status: RunStatus.default("running"),

    /** The LLM used. Replay tests run against both models. */
    model_name: z.string(),
    lookahead_h: z.number().int().positive().default(72),
    tier: z.string().default("commit"),

    /* headline counters the demo narrates */
    scanned_count: z.number().int().min(0).default(0),
    flagged_count: z.number().int().min(0).default(0),
    conflicts_count: z.number().int().min(0).default(0),
    resolved_count: z.number().int().min(0).default(0),
    escalated_count: z.number().int().min(0).default(0),

    conflicts: z.array(Conflict).default([]),
    /** The full ordered trace. */
    steps: z.array(AgentStep).min(1),

    replay: z.boolean().default(true),
  })
  .superRefine((v, ctx) => {
    for (let i = 1; i < v.steps.length; i++) {
      if (v.steps[i].seq <= v.steps[i - 1].seq) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `step seq must be strictly increasing at index ${i}`,
          path: ["steps", i, "seq"],
        });
        break;
      }
    }
  });
export type AgentRun = z.infer<typeof AgentRun>;

/* -------------------------------------------------------------------------- */
/* UI helpers — T1, feel free to move these into the web app.                  */
/* -------------------------------------------------------------------------- */

export const STEP_TYPE_LABEL: Record<StepType, string> = {
  scan: "Scan",
  evaluate: "Evaluate",
  conflict: "Conflict",
  propose: "Propose",
  gate: "Policy gate",
  act: "Act",
  verify: "Verify",
  record: "Record",
  escalate: "Escalate",
};

export const GATE_DECISION_LABEL: Record<GateDecision, string> = {
  approve: "Approved",
  modify: "Approved (modified)",
  deny: "Denied — escalated",
};
