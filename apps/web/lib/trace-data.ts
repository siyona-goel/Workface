import agentRunJson from "@/data/agent-run.json";
import { faceName } from "@/lib/console-data";

export const STEP_TYPES = [
  "scan",
  "evaluate",
  "conflict",
  "propose",
  "gate",
  "act",
  "verify",
  "record",
  "escalate",
] as const;
export type StepType = (typeof STEP_TYPES)[number];

export const GATE_DECISIONS = ["approve", "modify", "deny"] as const;
export type GateDecision = (typeof GATE_DECISIONS)[number];

export const RUN_STATUSES = ["running", "completed", "failed"] as const;
export type RunStatus = (typeof RUN_STATUSES)[number];

export type ToolCall = {
  tool: string;
  args: Record<string, unknown>;
  ok: boolean;
  gated: boolean;
  result_summary: string | null;
  fg_activity_ids: string[];
  latency_ms: number | null;
};

export type GateVerdict = {
  decision: GateDecision;
  rule_id: string;
  reason: string;
  escalated: boolean;
  modified_params: Record<string, unknown> | null;
};

export type Proposal = {
  kind: string;
  activity_ids: string[];
  rationale: string;
  solver_payload: Record<string, unknown> | null;
  float_days_consumed: number | null;
  projected_verdict: string | null;
};

export type Conflict = {
  id: string;
  work_face_id: string;
  shift_date: string;
  competing_activity_ids: string[];
  compliant_hours: number;
  demanded_hours: number;
  description: string;
  resolved_by_step_seq: number | null;
};

export type AgentStep = {
  seq: number;
  type: StepType;
  at: string;
  title: string;
  detail: string | null;
  activity_ids: string[];
  conflict_id: string | null;
  tool_calls: ToolCall[];
  proposal: Proposal | null;
  gate: GateVerdict | null;
  record_seq: number | null;
};

export type AgentRun = {
  schema_version: string;
  run_id: string;
  site_id: string;
  started_at: string;
  finished_at: string | null;
  status: RunStatus;
  model_name: string;
  lookahead_h: number;
  tier: string;
  scanned_count: number;
  flagged_count: number;
  conflicts_count: number;
  resolved_count: number;
  escalated_count: number;
  conflicts: Conflict[];
  steps: AgentStep[];
  replay: boolean;
};

export const agentRun = agentRunJson as AgentRun;

/** Hand-written fixture IDs — not in activities.json. Labels from the T3 narrative. */
export const TRACE_ACTIVITY_LABEL: Record<string, string> = {
  "A-2003": "Slab pour",
  "A-2009": "Epoxy coating",
  "A-2006": "Deck weld",
  "A-2009a": "Coating pass 1",
  "A-2009b": "Coating pass 2",
};

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

export type ConflictOutcome = "resolved" | "escalated" | "open";

export function conflictById(id: string) {
  return agentRun.conflicts.find((c) => c.id === id);
}

export function activityLabel(id: string) {
  return TRACE_ACTIVITY_LABEL[id] ?? id;
}

export function formatCompeting(ids: string[]) {
  return ids
    .map((id) => `${id} ${activityLabel(id)}`)
    .join(" vs ");
}

export function formatShiftDate(ymd: string) {
  const [year, month, day] = ymd.split("-").map(Number);
  if (!year || !month || !day) return ymd;
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    timeZone: "UTC",
  });
}

export function conflictOutcome(conflict: Conflict): ConflictOutcome {
  const steps = agentRun.steps.filter((s) => s.conflict_id === conflict.id);
  if (steps.some((s) => s.type === "escalate" || s.gate?.escalated)) {
    return "escalated";
  }
  if (steps.some((s) => s.type === "verify" || s.type === "act")) {
    return "resolved";
  }
  return "open";
}

export function conflictHeadline(conflict: Conflict) {
  return `${formatCompeting(conflict.competing_activity_ids)} · ${faceName(conflict.work_face_id)}`;
}

export type StepGroup = {
  conflictId: string | null;
  steps: AgentStep[];
};

export function groupStepsByConflict(steps: AgentStep[]): StepGroup[] {
  const groups: StepGroup[] = [];
  for (const step of steps) {
    const last = groups[groups.length - 1];
    if (last && last.conflictId === step.conflict_id) {
      last.steps.push(step);
    } else {
      groups.push({ conflictId: step.conflict_id, steps: [step] });
    }
  }
  return groups;
}

/** Compress the fixture's wall-clock gaps into a short stream. */
export function streamDelayMs(prev: AgentStep | undefined, next: AgentStep) {
  if (!prev) return 220;
  const gap = Date.parse(next.at) - Date.parse(prev.at);
  if (!Number.isFinite(gap) || gap <= 0) return 320;
  return Math.min(720, Math.max(280, Math.round(gap / 18)));
}
