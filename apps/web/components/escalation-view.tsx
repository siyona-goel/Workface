"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { AppNav } from "@/components/app-nav";
import { SourceToggle } from "@/components/source-toggle";
import { escalationsFromRun, primaryEscalation, sampleGateVerdicts } from "@/lib/escalations";
import {
  GATE_DECISION_LABEL,
  activityLabel,
  type GateDecision,
} from "@/lib/trace-data";
import { useAgentEvents } from "@/lib/use-agent-events";
import { cn } from "@/lib/utils";

const DECISION_TONE: Record<GateDecision, string> = {
  approve: "border-emerald-300/45 bg-emerald-300/8",
  modify: "border-amber-300/45 bg-amber-300/8",
  deny: "border-red-300/55 bg-red-300/10",
};

export function EscalationView() {
  const { source, run, channelState } = useAgentEvents();
  const params = useSearchParams();
  const selected = primaryEscalation(run, params.get("c"));
  const all = escalationsFromRun(run);

  return (
    <div className="flex min-h-dvh flex-col bg-background text-foreground">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-border/70 px-3 py-2 sm:px-4 sm:py-2.5">
        <div className="flex items-baseline gap-3">
          <span className="text-sm font-semibold tracking-[0.22em]">
            WORKFACE
          </span>
          <span className="hidden text-xs text-muted-foreground sm:inline">
            Escalation
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
          <span className="rounded-sm border border-red-400/40 bg-red-400/10 px-1.5 py-0.5 font-medium tracking-wider text-red-200 uppercase">
            Gate denied
          </span>
          <span>{run.escalated_count} routed to a human</span>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <SourceToggle source={source} channelState={channelState} />
          <AppNav current="escalate" />
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-3 py-4 sm:px-4">
        {selected ? (
          <article className="rounded-xl border border-red-300/45 bg-red-300/8 px-4 py-4">
            <p className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
              Escalation — policy gate denied
            </p>
            <h1 className="mt-1 text-base font-semibold">
              {selected.escalate?.title ?? "Routed to the superintendent"}
            </h1>
            <p className="mt-2 font-mono text-[11px] text-muted-foreground">
              {selected.activity_ids
                .map((id) => `${id} ${activityLabel(id)}`)
                .join(" · ")}
              {selected.conflict
                ? ` · ${selected.conflict.id} · ${selected.conflict.shift_date}`
                : null}
            </p>
            {selected.escalate?.detail || selected.propose?.proposal?.rationale ? (
              <p className="mt-3 text-[13px] leading-relaxed">
                {selected.escalate?.detail ??
                  selected.propose?.proposal?.rationale}
              </p>
            ) : null}

            {selected.gate ? (
              <div className="mt-4 rounded-lg border border-red-300/40 bg-background/50 px-3 py-3">
                <p className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
                  Gate verdict
                </p>
                <p className="mt-1 text-sm font-semibold">
                  {GATE_DECISION_LABEL[selected.gate.decision]}
                </p>
                <p className="mt-2 text-[13px] leading-relaxed">
                  {selected.gate.reason}
                </p>
                <p className="mt-2 font-mono text-[12px] text-red-200">
                  rule_id: {selected.gate.rule_id}
                </p>
              </div>
            ) : (
              <p className="mt-4 text-[12px] text-muted-foreground">
                No gate payload on this escalation step.
              </p>
            )}
          </article>
        ) : (
          <p className="py-10 text-center text-sm text-muted-foreground">
            No escalation in this run.
          </p>
        )}

        {all.length > 1 ? (
          <section>
            <h2 className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
              All escalations
            </h2>
            <ul className="mt-2 flex flex-col gap-2">
              {all.map((item) => (
                <li key={item.id}>
                  <Link
                    href={`/escalate?c=${item.id}&src=${source}`}
                    className={cn(
                      "block rounded-lg border px-3 py-2 text-[12px]",
                      selected?.id === item.id
                        ? "border-red-300/50 bg-red-300/10"
                        : "border-border/70 hover:bg-muted/30",
                    )}
                  >
                    <span className="font-mono text-[10px] text-muted-foreground">
                      {item.id}
                    </span>
                    <span className="mt-0.5 block">
                      {item.escalate?.title ?? item.gate?.rule_id ?? item.id}
                    </span>
                    {item.gate ? (
                      <span className="mt-0.5 block font-mono text-[10px] text-muted-foreground">
                        {item.gate.rule_id}
                      </span>
                    ) : null}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        <section>
          <h2 className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
            Policy surface
          </h2>
          <p className="mt-1 text-[12px] text-muted-foreground">
            Day-5 gate-verdict fixture. The deny case is the demo beat — cheapest
            fix eats four days of float, so the agent escalates.
          </p>
          <ul className="mt-3 flex flex-col gap-2">
            {sampleGateVerdicts.map((verdict) => (
              <li
                key={`${verdict.decision}-${verdict.rule_id}-${verdict.reason.slice(0, 24)}`}
                className={cn(
                  "rounded-xl border px-3 py-3",
                  DECISION_TONE[verdict.decision],
                )}
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-[12px] font-semibold">
                    {GATE_DECISION_LABEL[verdict.decision]}
                  </span>
                  <span className="font-mono text-[11px] text-muted-foreground">
                    rule_id: {verdict.rule_id}
                  </span>
                </div>
                <p className="mt-1.5 text-[12px] leading-relaxed">
                  {verdict.reason}
                </p>
                {verdict.escalated ? (
                  <p className="mt-1 text-[11px] text-red-200">Routed to a human</p>
                ) : null}
              </li>
            ))}
          </ul>
        </section>

        <p className="border-t border-border/60 pt-3 text-[11px] leading-relaxed text-muted-foreground">
          Default source is T3&apos;s Day-5 fixtures. Switch to{" "}
          <span className="font-medium text-foreground">Live run</span> to use
          the gated loop T3 merged (`agent_run_live.json`). The Supabase channel{" "}
          <span className="font-mono">workface-agent</span> listens for{" "}
          <span className="font-mono">agent_step</span> inserts and broadcast{" "}
          <span className="font-mono">step</span> events.
        </p>
      </div>
    </div>
  );
}
