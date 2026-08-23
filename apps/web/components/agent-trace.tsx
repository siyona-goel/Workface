"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { AppNav } from "@/components/app-nav";
import { Button } from "@/components/ui/button";
import { TraceStepCard } from "@/components/trace-step-card";
import { faceName, formatWhen } from "@/lib/console-data";
import {
  agentRun,
  conflictHeadline,
  conflictOutcome,
  formatCompeting,
  formatShiftDate,
  groupStepsByConflict,
  streamDelayMs,
  type Conflict,
  type ConflictOutcome,
} from "@/lib/trace-data";
import { cn } from "@/lib/utils";

const OUTCOME_LABEL: Record<ConflictOutcome, string> = {
  resolved: "Resolved",
  escalated: "Escalated",
  open: "Open",
};

export function AgentTrace() {
  const [visibleCount, setVisibleCount] = useState(0);
  const [generation, setGeneration] = useState(0);
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const steps = agentRun.steps;
  const streaming = visibleCount < steps.length;

  useEffect(() => {
    if (visibleCount >= steps.length) return;
    const prev = steps[visibleCount - 1];
    const next = steps[visibleCount];
    const id = window.setTimeout(() => {
      setVisibleCount((n) => n + 1);
    }, streamDelayMs(prev, next));
    return () => window.clearTimeout(id);
  }, [generation, steps, visibleCount]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [visibleCount]);

  const visibleSteps = steps.slice(0, visibleCount);
  const groups = useMemo(
    () => groupStepsByConflict(visibleSteps),
    [visibleSteps],
  );

  function replay() {
    setVisibleCount(0);
    setGeneration((g) => g + 1);
  }

  function showAll() {
    setVisibleCount(steps.length);
  }

  function focusConflict(id: string) {
    setFocusedId((current) => (current === id ? null : id));
    const alreadyVisible = visibleSteps.some((s) => s.conflict_id === id);
    if (!alreadyVisible) setVisibleCount(steps.length);
  }

  useEffect(() => {
    if (!focusedId) return;
    document.getElementById(`conflict-group-${focusedId}`)?.scrollIntoView({
      block: "start",
      behavior: "smooth",
    });
  }, [focusedId, visibleCount]);

  return (
    <div className="flex h-dvh min-h-0 flex-col bg-background text-foreground">
      <header className="flex items-center gap-4 border-b border-border/70 px-4 py-2.5">
        <div className="flex items-baseline gap-3">
          <span className="text-sm font-semibold tracking-[0.22em]">
            WORKFACE
          </span>
          <span className="hidden text-xs text-muted-foreground sm:inline">
            Agent trace
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-2 text-[11px] text-muted-foreground">
          <span className="rounded-sm border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 font-medium tracking-wider text-emerald-200 uppercase">
            Replay
          </span>
          <span className="font-mono">{agentRun.run_id}</span>
          <span>
            {agentRun.scanned_count} scanned · {agentRun.flagged_count} flagged ·{" "}
            {agentRun.conflicts_count} conflicts
          </span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <AppNav current="trace" />
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(260px,320px)_minmax(0,1fr)]">
        <aside className="min-h-0 overflow-y-auto border-b border-border/70 lg:border-r lg:border-b-0">
          <div className="px-4 py-3">
            <h2 className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
              Conflicts
            </h2>
            <p className="mt-1 text-[11px] text-muted-foreground">
              Grouped by work face and shift. {agentRun.resolved_count} resolved
              · {agentRun.escalated_count} escalated.
            </p>
          </div>
          <ul className="flex flex-col gap-2 px-4 pb-4">
            {agentRun.conflicts.map((conflict) => (
              <li key={conflict.id}>
                <ConflictCard
                  conflict={conflict}
                  pressed={focusedId === conflict.id}
                  onToggle={() => focusConflict(conflict.id)}
                />
              </li>
            ))}
          </ul>
        </aside>

        <section className="flex min-h-0 flex-col">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/70 px-4 py-2">
            <div>
              <h2 className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
                Agent trace
              </h2>
              <p className="text-[11px] text-muted-foreground">
                Step-by-step, streams top to bottom · {formatWhen(agentRun.started_at)}
                {agentRun.finished_at
                  ? ` – ${formatWhen(agentRun.finished_at)}`
                  : ""}
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
                  ? agentRun.conflicts.find((c) => c.id === group.conflictId)
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

              {visibleCount === 0 ? (
                <p className="py-10 text-center text-sm text-muted-foreground">
                  Starting the replayed run…
                </p>
              ) : null}

              <div ref={endRef} />

              <p className="rounded-xl border border-border/70 bg-card/30 px-3.5 py-3 text-[11px] leading-relaxed text-muted-foreground">
                {streaming
                  ? `Streaming ${visibleCount} of ${steps.length} steps from the Day-5 fixture.`
                  : "Replay complete. Built against T3 Day-5 fixtures, not the live loop. Day 7 pushes this over Supabase realtime."}
              </p>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function ConflictCard({
  conflict,
  pressed,
  onToggle,
}: {
  conflict: Conflict;
  pressed: boolean;
  onToggle: () => void;
}) {
  const outcome = conflictOutcome(conflict);

  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={pressed}
      className={cn(
        "w-full rounded-xl border px-3 py-2.5 text-left transition-colors",
        outcome === "escalated"
          ? "border-red-300/45 bg-red-300/8"
          : "border-amber-300/45 bg-amber-300/8",
        pressed && "ring-1 ring-foreground/20",
      )}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-mono text-[10px] text-muted-foreground">
          {conflict.id} · {formatShiftDate(conflict.shift_date)}
        </span>
        <span
          className={cn(
            "text-[10px] font-medium tracking-wide uppercase",
            outcome === "escalated" ? "text-red-200" : "text-emerald-200",
          )}
        >
          {OUTCOME_LABEL[outcome]}
        </span>
      </div>
      <p className="mt-1 text-[12px] font-medium leading-snug">
        {formatCompeting(conflict.competing_activity_ids)}
      </p>
      <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
        {conflict.demanded_hours} h demanded · {conflict.compliant_hours} h open
      </p>
      <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
        {conflictHeadline(conflict)}
      </p>
    </button>
  );
}
