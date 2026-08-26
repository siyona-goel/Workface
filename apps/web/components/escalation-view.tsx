"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { AppNav, WorkfaceHomeLink } from "@/components/app-nav";
import { SourceToggle } from "@/components/source-toggle";
import {
  GATE_RAIL,
  GATE_TEXT,
  GateStatusLabel,
  GateVerdictPanel,
  StatusRailCard,
} from "@/components/status-rail";
import { escalationsFromRun, primaryEscalation, sampleGateVerdicts } from "@/lib/escalations";
import { activityLabel } from "@/lib/trace-data";
import { useAgentEvents } from "@/lib/use-agent-events";
import { cn } from "@/lib/utils";

export function EscalationView() {
  const { source, run, channelState } = useAgentEvents();
  const params = useSearchParams();
  const selected = primaryEscalation(run, params.get("c"));
  const all = escalationsFromRun(run);
  const selectedDecision = selected?.gate?.decision ?? "deny";

  return (
    <div className="flex min-h-dvh flex-col bg-background text-foreground">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-border/70 px-3 py-2 sm:px-4 sm:py-2.5">
        <div className="flex items-baseline gap-3">
          <WorkfaceHomeLink />
          <span className="hidden text-xs text-muted-foreground sm:inline">
            Escalation
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
          <span className="rounded-sm border border-border/70 bg-card/30 px-1.5 py-0.5 font-medium tracking-wider uppercase">
            <span className={GATE_TEXT.deny}>Gate denied</span>
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
          <StatusRailCard railClass={GATE_RAIL[selectedDecision]} innerClassName="py-4">
            <p className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
              Escalation — policy gate
            </p>
            <h1 className="mt-1 text-base font-semibold tracking-tight">
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
              <p className="mt-3 text-[13px] leading-relaxed text-foreground/90">
                {selected.escalate?.detail ??
                  selected.propose?.proposal?.rationale}
              </p>
            ) : null}

            {selected.gate ? (
              <GateVerdictPanel gate={selected.gate} />
            ) : (
              <p className="mt-4 text-[12px] text-muted-foreground">
                No gate payload on this escalation step.
              </p>
            )}
          </StatusRailCard>
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
              {all.map((item) => {
                const decision = item.gate?.decision ?? "deny";
                const isSelected = selected?.id === item.id;
                return (
                  <li key={item.id}>
                    <Link
                      href={`/escalate?c=${item.id}&src=${source}`}
                      className={cn(
                        "relative block overflow-hidden rounded-lg border bg-card/25 transition-colors",
                        isSelected
                          ? "border-border bg-muted/20"
                          : "border-border/70 hover:bg-muted/15",
                      )}
                    >
                      <div
                        aria-hidden
                        className={cn(
                          "absolute inset-y-0 left-0 w-[3px]",
                          GATE_RAIL[decision],
                        )}
                      />
                      <div className="py-2.5 pr-3 pl-4 text-[12px]">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-mono text-[10px] text-muted-foreground">
                            {item.id}
                          </span>
                          {item.gate ? (
                            <GateStatusLabel decision={item.gate.decision} />
                          ) : null}
                        </div>
                        <span className="mt-0.5 block text-foreground/90">
                          {item.escalate?.title ?? item.gate?.rule_id ?? item.id}
                        </span>
                        {item.gate ? (
                          <span className="mt-0.5 block font-mono text-[10px] text-muted-foreground">
                            rule_id: {item.gate.rule_id}
                          </span>
                        ) : null}
                      </div>
                    </Link>
                  </li>
                );
              })}
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
              <li key={`${verdict.decision}-${verdict.rule_id}-${verdict.reason.slice(0, 24)}`}>
                <StatusRailCard railClass={GATE_RAIL[verdict.decision]}>
                  <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                    <GateStatusLabel decision={verdict.decision} />
                    <span className="font-mono text-[11px] text-muted-foreground">
                      rule_id: {verdict.rule_id}
                    </span>
                  </div>
                  <p className="mt-2 text-[12px] leading-relaxed text-foreground/90">
                    {verdict.reason}
                  </p>
                  {verdict.escalated ? (
                    <p className="mt-2 text-[10px] font-medium tracking-[0.12em] text-muted-foreground uppercase">
                      Routed to a human
                    </p>
                  ) : null}
                </StatusRailCard>
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
