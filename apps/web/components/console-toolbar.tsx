import type { ReactNode } from "react";

import { WindowChip } from "@/components/window-chip";
import {
  VERDICTS,
  consoleData,
  type ConsoleFilters,
  type Verdict,
} from "@/lib/console-data";
import { cn } from "@/lib/utils";

type Props = {
  filters: ConsoleFilters;
  onChange: (next: ConsoleFilters) => void;
  verdictCounts: Record<Verdict, number>;
  resultCount: number;
};

const selectClass =
  "h-8 max-w-[220px] truncate rounded-md border border-border bg-background/60 px-2 text-xs text-foreground outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40";

export function ConsoleToolbar({
  filters,
  onChange,
  verdictCounts,
  resultCount,
}: Props) {
  const facesByStructure = groupFaces();

  function toggleVerdict(v: Verdict) {
    const next = new Set(filters.verdicts);
    if (next.has(v)) next.delete(v);
    else next.add(v);
    onChange({ ...filters, verdicts: next });
  }

  return (
    <div className="flex flex-col gap-3 border-b border-border/70 bg-card/40 px-4 py-3">
      <div className="flex items-end gap-3">
        <label className="flex min-w-40 flex-col gap-1">
          <span className="text-[10px] font-medium tracking-[0.14em] text-muted-foreground uppercase">
            Trade
          </span>
          <select
            className={selectClass}
            value={filters.tradeId ?? ""}
            onChange={(e) =>
              onChange({ ...filters, tradeId: e.target.value || null })
            }
          >
            <option value="">All trades</option>
            {consoleData.trades.map((t) => (
              <option key={t.trade_id} value={t.trade_id}>
                {t.display_name}
              </option>
            ))}
          </select>
        </label>

        <label className="flex min-w-40 flex-col gap-1">
          <span className="text-[10px] font-medium tracking-[0.14em] text-muted-foreground uppercase">
            Work face
          </span>
          <select
            className={selectClass}
            value={filters.workFaceId ?? ""}
            onChange={(e) =>
              onChange({ ...filters, workFaceId: e.target.value || null })
            }
          >
            <option value="">All work faces</option>
            {facesByStructure.map(([structure, faces]) => (
              <optgroup key={structure} label={structure}>
                {faces.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>

        <div className="flex shrink-0 items-center gap-1.5 pb-0.5">
          {VERDICTS.map((v) => (
            <WindowChip
              key={v}
              verdict={v}
              count={verdictCounts[v]}
              pressed={
                filters.verdicts.size === 0 || filters.verdicts.has(v)
              }
              onToggle={() => toggleVerdict(v)}
            />
          ))}
        </div>

        <div className="ml-auto flex shrink-0 items-center gap-2 pb-0.5">
          <Toggle
            pressed={filters.lookaheadOnly}
            onClick={() =>
              onChange({ ...filters, lookaheadOnly: !filters.lookaheadOnly })
            }
          >
            24–27 Aug lookahead
          </Toggle>
          <Toggle
            pressed={filters.thermalOnly}
            onClick={() =>
              onChange({ ...filters, thermalOnly: !filters.thermalOnly })
            }
          >
            Thermal only
          </Toggle>
          <span className="font-mono text-[11px] text-muted-foreground tabular-nums">
            {resultCount} shown
          </span>
        </div>
      </div>
    </div>
  );
}

function Toggle({
  pressed,
  onClick,
  children,
}: {
  pressed: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={cn(
        "h-7 rounded-md border px-2 text-[11px] font-medium transition-colors",
        pressed
          ? "border-primary/40 bg-primary/15 text-foreground"
          : "border-border text-muted-foreground hover:bg-muted/40",
      )}
    >
      {children}
    </button>
  );
}

function groupFaces() {
  const map = new Map<string, typeof consoleData.work_faces>();
  for (const face of consoleData.work_faces) {
    const list = map.get(face.structure_id) ?? [];
    list.push(face);
    map.set(face.structure_id, list);
  }
  return [...map.entries()];
}
