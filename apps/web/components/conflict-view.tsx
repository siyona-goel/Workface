"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { AppNav } from "@/components/app-nav";
import { ConflictCard, OUTCOME_LABEL } from "@/components/conflict-card";
import { SourceToggle } from "@/components/source-toggle";
import { faceName } from "@/lib/console-data";
import { conflictOutcome, formatShiftDate, type ConflictOutcome } from "@/lib/trace-data";
import { useAgentEvents } from "@/lib/use-agent-events";
import { cn } from "@/lib/utils";

const FILTERS: Array<ConflictOutcome | "all"> = [
  "all",
  "escalated",
  "resolved",
  "open",
];

export function ConflictView() {
  const { source, run, channelState } = useAgentEvents();
  const [filter, setFilter] = useState<ConflictOutcome | "all">("all");

  const rows = useMemo(() => {
    return run.conflicts.filter((c) => {
      if (filter === "all") return true;
      return conflictOutcome(c, run) === filter;
    });
  }, [filter, run]);

  const grouped = useMemo(() => {
    const map = new Map<string, typeof rows>();
    for (const c of rows) {
      const list = map.get(c.work_face_id) ?? [];
      list.push(c);
      map.set(c.work_face_id, list);
    }
    return [...map.entries()];
  }, [rows]);

  const counts = useMemo(() => {
    const out = { all: run.conflicts.length, escalated: 0, resolved: 0, open: 0 };
    for (const c of run.conflicts) out[conflictOutcome(c, run)] += 1;
    return out;
  }, [run]);

  return (
    <div className="flex min-h-dvh flex-col bg-background text-foreground">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-border/70 px-3 py-2 sm:px-4 sm:py-2.5">
        <div className="flex items-baseline gap-3">
          <span className="text-sm font-semibold tracking-[0.22em]">
            WORKFACE
          </span>
          <span className="hidden text-xs text-muted-foreground sm:inline">
            Conflicts
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
          <span>
            {run.conflicts_count} conflicts · {run.resolved_count} resolved ·{" "}
            {run.escalated_count} escalated
          </span>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <SourceToggle source={source} channelState={channelState} />
          <AppNav current="conflicts" />
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-3 py-4 sm:px-4">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h1 className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
              Conflict queue
            </h1>
            <p className="text-[12px] text-muted-foreground">
              Grouped by work face and shift. Escalated rows open the gate
              verdict.
            </p>
          </div>
          <div className="flex flex-wrap gap-1">
            {FILTERS.map((id) => (
              <button
                key={id}
                type="button"
                onClick={() => setFilter(id)}
                className={cn(
                  "rounded-md border px-2 py-0.5 text-[11px] font-medium",
                  filter === id
                    ? "border-border bg-muted/30 text-foreground"
                    : "border-border/70 text-muted-foreground hover:bg-muted/15",
                )}
              >
                {id === "all" ? "All" : OUTCOME_LABEL[id]} {counts[id]}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-6">
          {grouped.map(([faceId, conflicts]) => (
            <section key={faceId}>
              <h2 className="mb-2 text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
                {faceName(faceId)} · {faceId}
              </h2>
              <ul className="grid gap-2 sm:grid-cols-2">
                {conflicts.map((conflict) => {
                  const outcome = conflictOutcome(conflict, run);
                  const href =
                    outcome === "escalated"
                      ? `/escalate?c=${conflict.id}&src=${source}`
                      : `/trace?src=${source}#conflict-group-${conflict.id}`;
                  return (
                    <li key={conflict.id}>
                      <Link href={href} className="block">
                        <ConflictCard conflict={conflict} run={run} />
                      </Link>
                      <p className="mt-1 px-1 font-mono text-[10px] text-muted-foreground">
                        {formatShiftDate(conflict.shift_date)} · {conflict.description}
                      </p>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
          {rows.length === 0 ? (
            <p className="py-10 text-center text-sm text-muted-foreground">
              No conflicts match this filter.
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
