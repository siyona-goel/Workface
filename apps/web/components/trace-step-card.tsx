import {
  GATE_DECISION_LABEL,
  STEP_TYPE_LABEL,
  activityLabel,
  type AgentStep,
  type StepType,
} from "@/lib/trace-data";
import { cn } from "@/lib/utils";

const TYPE_TONE: Record<StepType, string> = {
  scan: "border-border/70 bg-card/40",
  evaluate: "border-border/70 bg-card/40",
  conflict: "border-amber-300/55 bg-amber-300/10",
  propose: "border-sky-300/40 bg-sky-300/8",
  gate: "border-border/70 bg-card/40",
  act: "border-emerald-300/45 bg-emerald-300/8",
  verify: "border-emerald-300/35 bg-card/40",
  record: "border-border/70 bg-card/40",
  escalate: "border-red-300/55 bg-red-300/10",
};

function cardTone(step: AgentStep) {
  if (step.type === "gate" && step.gate?.decision === "deny") {
    return "border-red-300/55 bg-red-300/10";
  }
  if (step.type === "gate" && step.gate?.decision === "approve") {
    return "border-emerald-300/45 bg-emerald-300/8";
  }
  if (step.type === "gate" && step.gate?.decision === "modify") {
    return "border-amber-300/45 bg-amber-300/8";
  }
  return TYPE_TONE[step.type];
}

function typeLabel(step: AgentStep) {
  if (step.type === "conflict") return "Conflict detected — grouped";
  if (step.type === "escalate") return "Escalate — policy gate denied";
  if (step.type === "gate" && step.gate) {
    return `Gate — ${GATE_DECISION_LABEL[step.gate.decision]}`;
  }
  return STEP_TYPE_LABEL[step.type];
}

type Props = {
  step: AgentStep;
};

export function TraceStepCard({ step }: Props) {
  return (
    <article
      id={`step-${step.seq}`}
      className={cn(
        "animate-in fade-in slide-in-from-top-2 rounded-xl border px-3.5 py-3 duration-300",
        cardTone(step),
      )}
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-[11px] font-semibold tracking-[0.14em] uppercase">
          {typeLabel(step)}
        </h3>
        <time className="font-mono text-[10px] text-muted-foreground">
          {step.at.slice(11, 19)}
        </time>
      </header>
      <p className="mt-1.5 text-[13px] font-medium leading-snug">{step.title}</p>
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
        <blockquote className="mt-2 border-l-2 border-sky-300/50 pl-3 text-[12px] leading-relaxed text-foreground/90">
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

      {step.gate ? (
        <div className="mt-2 rounded-md border border-border/50 bg-background/40 px-2.5 py-2">
          <p className="text-[12px] leading-relaxed">{step.gate.reason}</p>
          <p className="mt-1 font-mono text-[10px] text-muted-foreground">
            rule_id: {step.gate.rule_id}
          </p>
        </div>
      ) : null}

      {step.tool_calls.length > 0 ? (
        <ul className="mt-2 flex flex-col gap-1">
          {step.tool_calls.map((call, i) => (
            <li
              key={`${call.tool}-${i}`}
              className="flex flex-wrap items-baseline gap-x-2 font-mono text-[10px] text-muted-foreground"
            >
              <span className="text-foreground/80">{call.tool}</span>
              {call.gated ? <span className="text-amber-200">gated</span> : null}
              {call.result_summary ? <span>{call.result_summary}</span> : null}
              {call.latency_ms != null ? <span>{call.latency_ms} ms</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}
