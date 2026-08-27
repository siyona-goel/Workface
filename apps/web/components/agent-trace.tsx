"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";

import { AppNav, WorkfaceHomeLink } from "@/components/app-nav";
import { ConflictCard } from "@/components/conflict-card";
import { SourceToggle } from "@/components/source-toggle";
import { TraceStepCard } from "@/components/trace-step-card";
import { Button } from "@/components/ui/button";
import { faceName, formatWhen } from "@/lib/console-data";
import {
  formatShiftDate,
  groupStepsByConflict,
} from "@/lib/trace-data";
import { useAgentEvents } from "@/lib/use-agent-events";
import { cn } from "@/lib/utils";

export function AgentTrace() {
  const {
    source,
    run,
    steps,
    visibleCount,
    streaming,
    channelState,
    channelStepCount,
    replay,
    showAll,
  } = useAgentEvents();
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [visibleCount, steps.length]);

  const groups = useMemo(() => groupStepsByConflict(steps), [steps]);

  function focusConflict(activityId: string) {
    setFocusedId((current) => (current === activityId ? null : activityId));
    if (!steps.some((s) => s.conflict_id === activityId)) showAll();
  }

  useEffect(() => {
    if (!focusedId) return;
    document.getElementById(`conflict-group-${focusedId}`)?.scrollIntoView({
      block: "start",
      behavior: "smooth",
    });
  }, [focusedId, steps.length]);

  return (
    <div className="flex min-h-dvh flex-col bg-background text-foreground lg:h-dvh lg:min-h-0 lg:overflow-hidden">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-border/70 px-3 py-2 sm:px-4 sm:py-2.5">
        <div className="flex items-baseline gap-3">
          <WorkfaceHomeLink />
          <span className="hidden text-xs text-muted-foreground sm:inline">
            Agent trace
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
          <span className="hidden sm:inline">
            {run.scanned_count} scanned · {run.flagged_count} flagged ·{" "}
            {run.conflicts_count} conflicts
          </span>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <SourceToggle source={source} channelState={channelState} />
          <AppNav current="trace" />
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col lg:grid lg:grid-cols-[minmax(240px,320px)_minmax(0,1fr)]">
        <aside className="max-h-[220px] shrink-0 overflow-y-auto border-b border-border/70 lg:max-h-none lg:border-r lg:border-b-0">
          <div className="px-3 py-3 sm:px-4">
            <h2 className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
              Conflicts
            </h2>
            <p className="mt-1 hidden text-[11px] text-muted-foreground sm:block">
              Grouped by work face and shift. {run.resolved_count} resolved ·{" "}
              {run.escalated_count} escalated.{" "}
              <Link href={`/conflicts?src=${source}`} className="underline">
                Open queue
              </Link>
            </p>
          </div>
          <ul className="flex gap-2 overflow-x-auto px-3 pb-4 sm:px-4 lg:flex-col lg:overflow-x-visible">
            {run.conflicts.map((conflict) => (
              <li key={conflict.id} className="min-w-[220px] lg:min-w-0">
                <ConflictCard
                  conflict={conflict}
                  run={run}
                  pressed={focusedId === conflict.id}
                  onToggle={() => focusConflict(conflict.id)}
                />
              </li>
            ))}
          </ul>
        </aside>

        <section className="flex min-h-0 flex-col">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/70 px-3 py-2 sm:px-4">
            <div>
              <h2 className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
                Agent trace
              </h2>
              <p className="text-[11px] text-muted-foreground">
                Step-by-step, streams top to bottom · {formatWhen(run.started_at)}
                {run.finished_at ? ` – ${formatWhen(run.finished_at)}` : ""}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="xs" onClick={replay}>
                Replay stream
              </Button>
              <Button
                variant="ghost"
                size="xs"
                onClick={showAll}
                disabled={!streaming}
              >
                Show all
              </Button>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
            <div className="mx-auto flex max-w-2xl flex-col gap-4">
              {groups.map((group) => {
                const dimmed =
                  focusedId != null &&
                  group.conflictId != null &&
                  group.conflictId !== focusedId;
                const conflict = group.conflictId
                  ? run.conflicts.find((c) => c.id === group.conflictId)
                  : undefined;

                return (
                  <div
                    key={group.conflictId ?? `open-${group.steps[0]?.seq}`}
                    id={
                      group.conflictId
                        ? `conflict-group-${group.conflictId}`
                        : undefined
                    }
                    className={cn(
                      "flex flex-col gap-2 transition-opacity",
                      dimmed && "opacity-35",
                    )}
                  >
                    {conflict ? (
                      <p className="px-1 text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
                        {conflict.id} · {faceName(conflict.work_face_id)} ·{" "}
                        {formatShiftDate(conflict.shift_date)}
                      </p>
                    ) : null}
                    {group.steps.map((step) => (
                      <TraceStepCard key={step.seq} step={step} />
                    ))}
                  </div>
                );
              })}

              {visibleCount === 0 && channelStepCount === 0 ? (
                <p className="py-10 text-center text-sm text-muted-foreground">
                  Waiting for the first agent event…
                </p>
              ) : null}

              <div ref={endRef} />

              <p className="rounded-lg border border-border/70 bg-card/25 px-3.5 py-3 text-[11px] leading-relaxed text-muted-foreground">
                {streaming
                  ? `Streaming ${visibleCount} of ${run.steps.length} steps (${source === "live" ? "T3 live run" : "Day-5 fixtures"}).`
                  : channelStepCount > 0
                    ? `${channelStepCount} live step${channelStepCount === 1 ? "" : "s"} arrived on the Supabase channel.`
                    : "Replay complete. Default is Day-5 fixtures. Live run is T3's gated loop."}
              </p>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
