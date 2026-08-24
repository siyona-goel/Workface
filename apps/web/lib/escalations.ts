import gateVerdictsJson from "@/data/gate-verdicts.json";
import {
  type AgentRun,
  type AgentStep,
  type Conflict,
  type GateVerdict,
  conflictOutcome,
} from "@/lib/trace-data";

export const sampleGateVerdicts = gateVerdictsJson as GateVerdict[];

export type Escalation = {
  id: string;
  conflict: Conflict | null;
  gate: GateVerdict | null;
  escalate: AgentStep | null;
  propose: AgentStep | null;
  activity_ids: string[];
};

export function escalationsFromRun(run: AgentRun): Escalation[] {
  const fromConflicts = run.conflicts
    .filter((c) => conflictOutcome(c, run) === "escalated")
    .map((conflict) => {
      const steps = run.steps.filter((s) => s.conflict_id === conflict.id);
      const gate = steps.find((s) => s.gate?.escalated)?.gate ?? null;
      const escalate = steps.find((s) => s.type === "escalate") ?? null;
      const propose =
        steps.find((s) => s.type === "propose" && s.proposal?.kind === "escalate") ??
        steps.find((s) => s.type === "propose") ??
        null;
      return {
        id: conflict.id,
        conflict,
        gate,
        escalate,
        propose,
        activity_ids: conflict.competing_activity_ids,
      };
    });

  const seen = new Set(
    fromConflicts
      .map((e) => e.escalate?.seq)
      .filter((n): n is number => n != null),
  );
  const orphans = run.steps
    .filter((s) => s.type === "escalate" && !s.conflict_id)
    .filter((s) => !seen.has(s.seq))
    .map((escalate) => {
      const gate =
        run.steps.find(
          (s) =>
            s.gate?.escalated &&
            s.activity_ids.some((id) => escalate.activity_ids.includes(id)),
        )?.gate ?? null;
      const propose =
        run.steps.find(
          (s) =>
            s.type === "propose" &&
            s.proposal?.kind === "escalate" &&
            s.activity_ids.some((id) => escalate.activity_ids.includes(id)),
        ) ?? null;
      return {
        id: escalate.activity_ids[0] ?? `seq-${escalate.seq}`,
        conflict: null,
        gate,
        escalate,
        propose,
        activity_ids: escalate.activity_ids,
      };
    });

  return [...fromConflicts, ...orphans];
}

export function primaryEscalation(
  run: AgentRun,
  id?: string | null,
): Escalation | undefined {
  const all = escalationsFromRun(run);
  if (id) return all.find((e) => e.id === id) ?? all[0];
  return all[0];
}
