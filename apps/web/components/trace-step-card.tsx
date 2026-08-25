import {
  GATE_DECISION_LABEL,
  STEP_TYPE_LABEL,
  activityLabel,
  type AgentStep,
  type StepType,
} from "@/lib/trace-data";
import {
  GATE_RAIL,
  GATE_TEXT,
  GateVerdictPanel,
  NEUTRAL_RAIL,
  StatusRailShell,
} from "@/components/status-rail";
import { cn } from "@/lib/utils";

const STEP_RAIL: Partial<Record<StepType, string>> = {
  conflict: "bg-amber-500",
  propose: "bg-sky-500",
  act: "bg-emerald-500",
  escalate: "bg-red-500",
};

const STEP_TEXT: Partial<Record<StepType, string>> = {
  conflict: "text-amber-400",
  propose: "text-sky-400",
  act: "text-emerald-400",
  escalate: "text-red-400",
};

function stepRailClass(step: AgentStep) {
  if (step.type === "gate" && step.gate) return GATE_RAIL[step.gate.decision];
  return STEP_RAIL[step.type] ?? NEUTRAL_RAIL;
}

function stepTypeLabel(step: AgentStep) {
  if (step.type === "conflict") return "Conflict detected";
  if (step.type === "escalate") return "Denied — escalated";
  if (step.type === "gate" && step.gate) {
    return GATE_DECISION_LABEL[step.gate.decision];
  }
  return STEP_TYPE_LABEL[step.type];
}

function stepLabelTone(step: AgentStep) {
  if (step.type === "gate" && step.gate) return GATE_TEXT[step.gate.decision];
  return STEP_TEXT[step.type] ?? "text-muted-foreground";
}

type Props = {
  step: AgentStep;
};

export function TraceStepCard({ step }: Props) {
  return (
    <StatusRailShell
      id={`step-${step.seq}`}
      railClass={stepRailClass(step)}
      innerClassName="py-3"
      className="animate-in fade-in slide-in-from-top-2 duration-300"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h3
          className={cn(
            "text-[10px] font-semibold tracking-[0.14em] uppercase",
            stepLabelTone(step),
          )}
        >
          {stepTypeLabel(step)}
        </h3>
        <time className="font-mono text-[10px] text-muted-foreground">
          {step.at.slice(11, 19)}
        </time>
      </header>
      <p className="mt-1.5 text-[13px] font-medium leading-snug text-foreground/95">
        {step.title}
      </p>
      {step.detail ? (
        <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
          {step.detail}
        </p>
      ) : null}

      {step.activity_ids.length > 0 ? (
        <p className="mt-2 font-mono text-[10px] text-muted-foreground">
          {step.activity_ids
            .map((id) => `${id} ${activityLabel(id)}`)
            .join(" · ")}
        </p>
      ) : null}

      {step.proposal ? (
        <blockquote className="mt-2 border-l-2 border-border/70 pl-3 text-[12px] leading-relaxed text-foreground/90">
          {step.proposal.rationale}
          {step.proposal.float_days_consumed != null ? (
            <span className="mt-1 block font-mono text-[10px] text-muted-foreground">
              float {step.proposal.float_days_consumed} d · {step.proposal.kind}
              {step.proposal.projected_verdict
                ? ` → ${step.proposal.projected_verdict}`
                : ""}
            </span>
          ) : null}
        </blockquote>
      ) : null}

      {step.gate ? <GateVerdictPanel gate={step.gate} /> : null}

      {step.tool_calls.length > 0 ? (
        <ul className="mt-2 flex flex-col gap-1">
          {step.tool_calls.map((call, i) => (
            <li
              key={`${call.tool}-${i}`}
              className="flex flex-wrap items-baseline gap-x-2 font-mono text-[10px] text-muted-foreground"
            >
              <span className="text-foreground/80">{call.tool}</span>
              {call.gated ? (
                <span className="text-[10px] font-semibold tracking-[0.12em] text-amber-400 uppercase">
                  gated
                </span>
              ) : null}
              {call.result_summary ? <span>{call.result_summary}</span> : null}
              {call.latency_ms != null ? <span>{call.latency_ms} ms</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </StatusRailShell>
  );
}
